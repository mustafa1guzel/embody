"""Replaceable model boundary. Mock output is never labelled live reasoning."""
from __future__ import annotations
from dataclasses import dataclass
import copy
import json
import os
from typing import Protocol

from core.agent.credentials import CredentialsMissing, ModelRequestError, create_openai_client


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelTurn:
    text: str = ''
    tool_calls: tuple[ToolCall, ...] = ()
    provider_items: tuple[dict, ...] = ()


class ModelAdapter(Protocol):
    mode: str

    def complete(self, messages: tuple[dict, ...], tool_schemas: tuple[dict, ...]) -> ModelTurn: ...


class MockModelAdapter:
    """Caller-supplied deterministic turns/callbacks, not a controller solver."""
    mode = 'deterministic_mock'

    def __init__(self, turns):
        self._turns = iter(turns)
        self.calls = 0

    def complete(self, messages, tool_schemas):
        self.calls += 1
        turn = next(self._turns)
        return turn(messages, tool_schemas) if callable(turn) else turn


def live_integration_status():
    configured = bool(os.environ.get('OPENAI_API_KEY', '').strip())
    return {'status': 'BLOCKED' if not configured else 'NOT_TESTED',
            'credentials_configured': configured,
            'reason': 'OPENAI_API_KEY is missing' if not configured else 'Day 4A does not make live requests'}


class OpenAIResponsesAdapter:
    """Optional injected Responses client; no SDK import/download on the offline path.

    Connecting a real client later changes this adapter only, not tool contracts.
    Tests inject an explicitly mocked transport; they do not verify live GPT use.
    """
    def __init__(self, client, model: str, *, mock_transport: bool = False, continuation='manual'):
        if not isinstance(model, str) or not model.strip():
            raise ValueError('An explicit model name is required')
        self.client, self.model = client, model
        self.requests_made = 0
        if continuation not in ('manual', 'server'):
            raise ValueError('Unknown continuation strategy')
        self.continuation = continuation
        self._previous_response_id = None
        self._consumed_messages = ()
        self._pending_calls = set()
        self.mode = 'mock_openai_transport' if mock_transport else 'openai_responses'

    @classmethod
    def from_environment(cls, model: str, *, env_path=None):
        if not isinstance(model, str) or not model.strip():
            raise ValueError('An explicit model name is required')
        return cls(create_openai_client(env_path), model, continuation='server')

    def close(self):
        self.client.close()

    def _request(self, **request):
        return self.client.responses.create(**request)

    def _build_request(self, messages, tool_schemas):
        pending = set(self._pending_calls)
        if self.continuation == 'server':
            consumed = self._consumed_messages
            if tuple(messages[:len(consumed)]) != consumed:
                raise ValueError('Conversation history changed; create a new adapter')
            current = messages[len(consumed):]
            instructions = '\n\n'.join(m['content'] for m in messages if m['role'] in ('system', 'developer'))
        else:
            current = messages
        inputs = []
        for message in current:
            if self.continuation == 'server' and message['role'] in ('system', 'developer', 'assistant'):
                continue
            if message.get('provider_items'):
                # Manual replay is a separate strategy, never combined with a
                # previous_response_id. Normalize SDK output to API input fields.
                inputs.extend(_replay_item(item) for item in message['provider_items'])
            elif message['role'] == 'tool':
                call_id = message.get('tool_call_id')
                if not isinstance(call_id, str) or not call_id.strip():
                    raise ValueError('Tool output requires the exact model call_id')
                if self.continuation == 'server':
                    if call_id not in pending:
                        raise ValueError('Unknown or duplicate tool call_id')
                    pending.remove(call_id)
                output = message['content']
                if not isinstance(output, str):
                    raise ValueError('Tool output must be a serialized string')
                inputs.append({'type': 'function_call_output', 'call_id': call_id, 'output': output})
            else:
                if message.get('content'):
                    inputs.append({'role': message['role'], 'content': message['content']})
                inputs.extend({'type': 'function_call', 'call_id': c['call_id'], 'name': c['name'],
                               'arguments': json.dumps(c['arguments'], allow_nan=False)}
                              for c in message.get('tool_calls', []))
        if self.continuation == 'server' and pending:
            raise ValueError('All outstanding tool calls require outputs before continuation')
        request = {'model': self.model, 'input': inputs, 'tools': list(tool_schemas)}
        if self.continuation == 'server':
            request.update(instructions=instructions, store=True)
            if self._previous_response_id:
                request['previous_response_id'] = self._previous_response_id
        json.dumps(request, allow_nan=False)  # Validate before any paid request.
        return request

    def complete(self, messages, tool_schemas):
        request = self._build_request(messages, tool_schemas)
        self.requests_made += 1
        try:
            response = self._request(**request)
        except Exception:
            # The orchestration trace records exception messages. Never forward
            # provider bodies, headers or SDK exception text into that trace.
            raise ModelRequestError('OpenAI request failed; provider details suppressed') from None
        output = [item if isinstance(item, dict) else item.model_dump(mode='json') for item in response.output]
        calls = []
        text = []
        for item in output:
            if item['type'] == 'function_call':
                if not isinstance(item.get('call_id'), str) or not item['call_id'].strip():
                    raise ValueError('Model function call is missing call_id')
                if item['call_id'] in {c.call_id for c in calls}:
                    raise ValueError('Model returned duplicate call IDs')
                arguments = json.loads(item['arguments'])
                if not isinstance(arguments, dict):
                    raise ValueError('Model tool arguments must decode to an object')
                calls.append(ToolCall(item['call_id'], item['name'], arguments))
            elif item['type'] == 'message':
                text.extend(c['text'] for c in item.get('content', []) if c['type'] == 'output_text')
        if self.continuation == 'server':
            response_id = getattr(response, 'id', None)
            if not isinstance(response_id, str) or not response_id:
                raise ValueError('Stored response is missing its response ID')
            self._previous_response_id = response_id
            self._consumed_messages = copy.deepcopy(tuple(messages))
            self._pending_calls = {c.call_id for c in calls}
        # Preserve genuine provider output for evidence, even when the server
        # retains reasoning and function calls and they need not be replayed.
        return ModelTurn('\n'.join(text), tuple(calls), tuple(output))


def _replay_item(item):
    allowed = {'function_call': ('type', 'id', 'call_id', 'name', 'arguments', 'status'),
               'reasoning': ('type', 'id', 'summary', 'encrypted_content'),
               'message': ('type', 'id', 'role', 'content', 'status', 'phase')}
    if item.get('type') not in allowed:
        raise ValueError('Unsupported manual replay item')
    return {k: copy.deepcopy(item[k]) for k in allowed[item['type']] if item.get(k) is not None}

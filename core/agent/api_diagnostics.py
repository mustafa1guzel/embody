"""Bounded API validation diagnostics, excluding headers and sensitive content."""
import os
import re


def payload_structure(request):
    return {'fields': sorted(request), 'previous_response_id_present': bool(request.get('previous_response_id')),
            'store': request.get('store'), 'tool_count': len(request.get('tools', [])),
            'input': [{'type': item.get('type', 'message'), 'role': item.get('role'),
                       'fields': sorted(item), 'output_type': type(item.get('output')).__name__,
                       'output_bytes': len(item['output'].encode()) if isinstance(item.get('output'), str) else None}
                      for item in request.get('input', [])]}


def sanitized_error(exc, request, *, api_key=None):
    # Never use str(exc): SDK exception text can contain entire provider bodies.
    body = getattr(exc, 'body', None)
    body = body if isinstance(body, dict) else {}
    error = body.get('error', body)
    error = error if isinstance(error, dict) else {}
    secrets = [v for v in os.environ.values() if isinstance(v, str) and len(v) >= 4]
    if isinstance(api_key, str) and api_key:
        secrets.append(api_key)
        if len(api_key) >= 16:
            secrets.extend((api_key[:12], api_key[-8:]))
    secrets.extend(item['content'] for item in request.get('input', [])
                   if isinstance(item.get('content'), str) and len(item['content']) >= 4)
    secrets.extend(item['output'] for item in request.get('input', [])
                   if isinstance(item.get('output'), str) and len(item['output']) >= 4)

    def clean(value):
        if not isinstance(value, str):
            return None
        for secret in sorted(set(secrets), key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        value = re.sub(r'(?i)bearer\s+[^\s,;\"\']+', 'Bearer [REDACTED]', value)
        value = re.sub(r'(?i)authorization\s*:[^\r\n]+', '[REDACTED HEADER]', value)
        value = re.sub(r'sk-[A-Za-z0-9_.*-]+', '[REDACTED]', value)
        value = ''.join(c if c.isprintable() else ' ' for c in value)
        return value[:2048]

    status = getattr(exc, 'status_code', None)
    return {'http_status': status if type(status) is int else None,
            'error_type': clean(error.get('type', getattr(exc, 'type', None))),
            'error_code': clean(error.get('code', getattr(exc, 'code', None))),
            'parameter': clean(error.get('param', getattr(exc, 'param', None))),
            'message': clean(error.get('message')),
            'request_id': clean(getattr(exc, 'request_id', None)),
            'payload_structure': payload_structure(request)}

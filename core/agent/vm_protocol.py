"""Bounded data-only wire format shared by the trusted host and Linux worker."""
import json
import math

MAX_FRAME = 262_144
MAX_STATE = 4096
VERSION = 1

class ProtocolError(ValueError):
    pass

def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProtocolError('Duplicate JSON key')
        result[key] = value
    return result

def decode(raw):
    if not isinstance(raw, bytes) or not raw.endswith(b'\n') or len(raw) > MAX_FRAME:
        raise ProtocolError('Invalid frame boundary or size')
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError('Nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError('Invalid JSON frame') from exc
    if not isinstance(value, dict):
        raise ProtocolError('Message must be an object')
    return value

def encode(value):
    try:
        raw = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProtocolError('Message cannot be encoded') from exc
    if len(raw) > MAX_FRAME:
        raise ProtocolError('Message exceeds bound')
    return raw

def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ProtocolError('Unexpected message fields')

def numbers(value, length):
    if (type(length) is not int or not 0 <= length <= MAX_STATE or not isinstance(value, list)
            or len(value) != length or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e12 for x in value)):
        raise ProtocolError('Invalid numeric vector')
    return value

def command_reply(reply, sequence, actuators):
    fields(reply, ('v', 'seq', 'ctrl'))
    if type(reply['v']) is not int or reply['v'] != VERSION or type(reply['seq']) is not int or reply['seq'] != sequence:
        raise ProtocolError('Version/sequence mismatch')
    return numbers(reply['ctrl'], actuators)

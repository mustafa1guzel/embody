"""Lazy, project-local credentials. Never export .env into the process environment."""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
import ssl
import stat

PROJECT_ENV_PATH = Path(__file__).resolve().parents[2] / '.env'
MAX_ENV_BYTES = 64 * 1024
OPENAI_BASE_URL = 'https://api.openai.com/v1'


class CredentialsMissing(RuntimeError):
    pass


class CredentialConfigurationError(RuntimeError):
    pass


class ModelRequestError(RuntimeError):
    """Safe public error: deliberately excludes provider bodies and exception text."""


def read_openai_api_key(env_path: Path | None = None) -> str:
    """Prefer an existing environment value, otherwise read only the project's file.

    No parent-directory discovery, interpolation, shell evaluation or environment
    mutation. Reject symlinks, nonregular files, oversized and nonprivate files.
    """
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        path = PROJECT_ENV_PATH if env_path is None else Path(env_path)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            raise CredentialsMissing('OPENAI_API_KEY is missing; no request was made') from None
        except OSError:
            raise CredentialConfigurationError('Cannot securely open project .env') from None
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise CredentialConfigurationError('Project .env must be an owner-only regular file (0600)')
            raw = stream.read(MAX_ENV_BYTES + 1)
        if len(raw) > MAX_ENV_BYTES:
            raise CredentialConfigurationError('Project .env exceeds the size limit')
        # Use the parser directly: no interpolation and no parser warning logging.
        from dotenv.parser import parse_stream
        try:
            bindings = list(parse_stream(io.StringIO(raw.decode('utf-8'))))
        except (UnicodeError, ValueError):
            raise CredentialConfigurationError('Project .env is invalid') from None
        if any(binding.error for binding in bindings):
            raise CredentialConfigurationError('Project .env is invalid')
        values = [b.value for b in bindings if b.key == 'OPENAI_API_KEY']
        if len(values) > 1:
            raise CredentialConfigurationError('Project .env contains duplicate API key entries')
        key = (values[0] or '').strip() if values else ''
    if not key:
        raise CredentialsMissing('OPENAI_API_KEY is missing; no request was made')
    if any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise CredentialConfigurationError('OPENAI_API_KEY has invalid characters')
    return key


def _disable_transport_logging():
    # SDK debug/error logs can include provider error bodies, including key hints.
    # Suppress only the SDK and its HTTP transports, including existing children.
    names = ('openai', 'httpx', 'httpcore', 'httpx2', 'httpcore2')
    for name in names:
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.disabled = True
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger) and name.startswith(tuple(n + '.' for n in names)):
            logger.disabled = True


def create_openai_client(env_path: Path | None = None):
    """Construct without making requests; pin the destination and disable retries.

    Proxy, base URL and CA overrides from the environment cannot redirect the key.
    The macOS system trust store covers Python installations lacking bundled CAs.
    """
    key = read_openai_api_key(env_path)
    _disable_transport_logging()
    from openai import OpenAI, DefaultHttpxClient
    _disable_transport_logging()
    ca_file = Path('/etc/ssl/cert.pem')
    context = ssl.create_default_context(cafile=str(ca_file) if ca_file.is_file() else None)
    transport = DefaultHttpxClient(verify=context, trust_env=False, follow_redirects=False, timeout=15.0)
    try:
        return OpenAI(api_key=key, base_url=OPENAI_BASE_URL, max_retries=0,
                      timeout=15.0, http_client=transport)
    except Exception:
        transport.close()
        raise ModelRequestError('OpenAI client initialization failed; details suppressed') from None

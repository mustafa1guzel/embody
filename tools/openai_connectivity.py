"""One authenticated, nongenerating API request. Never starts the agent loop."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from core.agent.credentials import create_openai_client


def check_connectivity():
    client = create_openai_client()
    report = {'endpoint': 'GET https://api.openai.com/v1/models',
              'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'requests_attempted': 1, 'automatic_retries': 0,
              'generation_requests': 0, 'agent_experiment_started': False}
    try:
        # Access the first page only. No auto-pagination and no model invocation.
        response = client.models.with_raw_response.list()
        report.update(status='PASS', http_status=response.status_code)
    except Exception as exc:
        # Authentication errors may echo a key fragment. Never persist str(exc),
        # headers, response bodies or tracebacks, even when this request fails.
        status = getattr(exc, 'status_code', None)
        report.update(status='FAIL', http_status=status if type(status) is int else None)
    finally:
        client.close()
    return report


def main():
    try:
        report = check_connectivity()
    except Exception:
        report = {'status': 'BLOCKED', 'requests_attempted': 0,
                  'reason': 'Credential or client setup failed; details suppressed',
                  'generation_requests': 0, 'agent_experiment_started': False}
    output = Path(__file__).resolve().parents[1] / 'artifacts/api_connectivity'
    output.mkdir(parents=True, exist_ok=True)
    path = output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with path.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

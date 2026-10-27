"""Append-only execution evidence, including failures and explicit mock provenance."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class ExecutionTrace:
    def __init__(self, path: Path, *, model_mode: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._previous = 0, None
        # Exclusive creation prevents accidentally mixing runs.
        self.path.open('x').close()
        self.append('execution_started', {'model_mode': model_mode})

    def append(self, event, payload):
        row = {'sequence': self._seq, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
               'event': event, 'payload': payload, 'previous_sha256': self._previous}
        row['sha256'] = digest_json(row)
        with self.path.open('a') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
            stream.flush()
        self._seq += 1
        self._previous = row['sha256']
        return row


def read_trace(path: Path):
    rows, previous = [], None
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        digest = row.pop('sha256')
        if row['sequence'] != len(rows) or row['previous_sha256'] != previous or digest_json(row) != digest:
            raise ValueError('Execution trace integrity mismatch')
        row['sha256'] = digest
        rows.append(row)
        previous = digest
    return rows

"""Read-only product view of an immutable, provenance-bound shape experiment."""
from pathlib import Path
from physics.contracts import digest
from engineering.project import identity
from engineering.store import Store
from workspace.data import bounded_read, decode_json
from .shape_live import validate_task


def load_review(service):
    root = service.root
    session = root / 'shape_agent_session.json'
    if not session.exists():
        return {'status': 'NO_SESSION'}
    data = decode_json(bounded_read(root, session.name))
    if set(data) != {'task', 'project_sha256', 'project_revision'} or identity(service.current()) != data['project_sha256'] or service.current()['revision'] != data['project_revision']:
        raise ValueError('Shape agent review is stale for the current authoritative head')
    pointer = root / 'shape_agent_review.json'
    if not pointer.exists():
        return {**data, 'status': 'PENDING_APPROVAL', 'origin': 'NO_MODEL_REQUEST', 'application_allowed': False}
    link = decode_json(bounded_read(root, pointer.name))
    if set(link) != {'record_sha256'}:
        raise ValueError('Exact immutable review reference required')
    record = Store(root / 'shape_agent_reviews').get(link['record_sha256'])
    if record['origin'] not in ('GENUINE_PROVIDER_RESPONSE', 'OFFLINE_PROTOCOL_FIXTURE', 'NO_PROVIDER_RESPONSE'):
        raise ValueError('Unsupported review provenance')
    proposal = record.get('proposal')
    if proposal:
        saved = service.proposals.get(proposal['proposal_id'])
        if digest(saved) != proposal['proposal_id'] or saved != {k: v for k, v in proposal.items() if k != 'proposal_id'}:
            raise ValueError('Review proposal differs from immutable engineering proposal')
        # UI never upgrades invalid/failed task measurements into a successful view.
        if record.get('validation', {}).get('status') == 'TYPED_TASK_GEOMETRY_NATIVE_COMPILE_PASS':
            if digest(validate_task(service, proposal)) != digest(record['validation']):
                raise ValueError('Independent review validation changed')
    if record.get('native'):
        native = record['native']
        if not proposal or native['proposal_id'] != proposal['proposal_id'] or native['proposed_project_sha256'] != proposal['resulting_project_sha256']:
            raise ValueError('Native result belongs to another proposal')
        # Read-only retrieval must not start another native rollout. Compare the
        # saved trusted result and its already recorded independent replay.
        relative = str((Path(native['evidence_path']) / 'result.json').relative_to(root))
        saved_result = decode_json(bounded_read(root, relative))
        inline = {k: v for k, v in native['result'].items() if k != 'native_render'}
        if digest(saved_result) != digest(inline) or saved_result['independent_verification']['status'] != 'PASS':
            raise ValueError('Native saved evidence differs from reviewed result')
    return {**data, **record, 'application_allowed': False, 'record_sha256': link['record_sha256']}


def publish_review(service, record):
    """Add review evidence only, never modify project data or permit application."""
    from robustness.contracts import write_once
    key = Store(service.root / 'shape_agent_reviews').put(record)
    write_once(service.root / 'shape_agent_review.json', {'record_sha256': key})
    return key

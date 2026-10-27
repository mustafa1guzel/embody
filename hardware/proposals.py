"""Reviewable data-only changes. No text-to-execution or implicit apply."""
import copy
from .assemblies import validate, identity, connect, remove_wire, fields
from .validation import inspect
from physics.contracts import digest


def propose(a, expected_sha256, operations, explanation, *, origin='manual_data_proposal'):
    if identity(a)!=expected_sha256:raise ValueError('Stale assembly; proposal must bind current identity')
    if not isinstance(operations,list) or not 1<=len(operations)<=16:raise ValueError('Bounded operations required')
    if not isinstance(explanation,str) or not 0<len(explanation)<=4000:raise ValueError('Explanation required')
    result=copy.deepcopy(a)
    for op in operations:
        if not isinstance(op,dict):raise ValueError('Invalid data operation')
        if op.get('kind')=='connect':
            fields(op,['kind','a','b']);result=connect(result,op['a'],op['b'])
        elif op.get('kind')=='disconnect':
            fields(op,['kind','wire_id']);result=remove_wire(result,op['wire_id'])
        else:raise ValueError('Only explicit wiring graph operations supported; no paths, code or execution')
    return {'schema_version':1,'base_sha256':expected_sha256,'proposed_sha256':identity(result),'assembly':validate(result),
        'operations':copy.deepcopy(operations),'explanation':explanation,'origin':origin,'diagnostics':inspect(result),
        'status':'PROPOSED_NOT_APPLIED','installation_effect':'NONE','independent_physical_verification':'NOT_RUN'}


def apply(a, proposal, confirmation):
    if confirmation!='APPLY WIRING CHANGE':raise ValueError('Explicit wiring review confirmation required')
    fields(proposal,['schema_version','base_sha256','proposed_sha256','assembly','operations','explanation','origin','diagnostics','status','installation_effect','independent_physical_verification'])
    rebuilt=propose(a,proposal['base_sha256'],proposal['operations'],proposal['explanation'],origin=proposal['origin'])
    # IDs for newly created connections are random; proposals must be replayed
    # semantically and their final exact graph separately validated.
    candidate=validate(proposal['assembly'])
    from .assemblies import netlist
    def normalized(x):return sorted(sorted(tuple(e) for e in ends) for ends in netlist(x).values())
    if identity(candidate)!=proposal['proposed_sha256'] or normalized(candidate)!=normalized(rebuilt['assembly']):raise ValueError('Proposal graph mismatch')
    before=copy.deepcopy(candidate);before['nets']=copy.deepcopy(a['nets']);before['wires']=copy.deepcopy(a['wires']);before['revision']=a['revision']
    if before!=a:raise ValueError('Proposal modified non-wiring properties')
    return candidate

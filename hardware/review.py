"""Narrow hardware review tools and separate data validation; no execution/apply."""
import copy
from types import SimpleNamespace
from .agent import HardwareTools
from .tool_contract import validate_proposal_arguments
from .assemblies import identity,validate,connect,remove_wire,netlist
from .validation import inspect


class HardwareReviewTools(HardwareTools):
    """Exactly one inspection and one proposal, with no delegated tool authority."""
    def __init__(self,trace,assembly,device_spec):
        super().__init__(SimpleNamespace(trace=trace,schemas=()),assembly,device_spec)
        self.inspected=False;self.inspection_attempts=0;self.proposal_attempts=0;self.submission=None

    def inspection_context(self):
        context=super().inspection_context()
        # Select authoritative wiring fields; no values or graph relationships
        # are inferred or changed. The generic HardwareTools view stays complete.
        used={c['part'] for c in self.assembly['components']}
        context['catalog']={key:{**{k:p[k] for k in ('id','model','manufacturer','confidence','properties','sources','assumptions')},
            'pins':[{k:pin[k] for k in ('id','role','required','voltage_v','high_min_v','capabilities')} for pin in p['pins']]}
            for key,p in context['catalog'].items() if key in used}
        context['catalog_scope']='Only installed parts, electrical fields, assumptions and sources; geometric representations omitted. Full catalog identity remains bound by circuitbase.catalog_sha256.'
        return context

    def dispatch(self,name,arguments):
        if name not in ('inspect_hardware','propose_hardware_change'):
            raise ValueError('Only hardware inspection and review-only proposal are authorized')
        if name=='inspect_hardware':
            if self.inspection_attempts:raise ValueError('One inspection maximum')
            self.inspection_attempts+=1
        else:
            if not self.inspected or self.proposal_attempts:raise ValueError('One proposal after inspection; no retry')
            self.proposal_attempts+=1
        result=super().dispatch(name,arguments)
        if name=='inspect_hardware':self.inspected=result['ok']
        else:self.submission={'arguments':copy.deepcopy(arguments),'output':copy.deepcopy(result)}
        return result


def independently_validate_proposal(assembly,arguments,proposal):
    """Rebuild actual operations in a copy, recompute graph/diagnostics, never apply."""
    validate_proposal_arguments(arguments);before=validate(assembly);base=identity(before)
    if arguments['expected_sha256']!=base or arguments['expected_revision']!=before['revision']:
        raise ValueError('Proposal does not bind the authorized assembly and revision')
    if (proposal['operations']!=arguments['operations'] or proposal['explanation']!=arguments['explanation']
            or proposal['base_sha256']!=base or proposal['status']!='PROPOSED_NOT_APPLIED'
            or proposal['installation_effect']!='NONE' or proposal['origin']!='model_tool_proposal_untrusted_data'):
        raise ValueError('Tool proposal does not match the actual model arguments/review boundary')
    rebuilt=copy.deepcopy(before)
    for op in arguments['operations']:
        rebuilt=remove_wire(rebuilt,op['wire_id']) if op['kind']=='disconnect' else connect(rebuilt,op['a'],op['b'])
    candidate=validate(proposal['assembly'])
    if identity(candidate)!=proposal['proposed_sha256']:raise ValueError('Proposed identity mismatch')
    # New/split net and wire IDs can be random. Compare real topology and exact
    # undirected edges, plus every non-wiring property and revision.
    def topology(a):return sorted(sorted(ends) for ends in netlist(a).values())
    def edges(a):return sorted(tuple(sorted((tuple(sorted(w['a'].items())),tuple(sorted(w['b'].items()))))) for w in a['wires'])
    unchanged=lambda a:{k:v for k,v in a.items() if k not in ('nets','wires')}
    if topology(candidate)!=topology(rebuilt) or edges(candidate)!=edges(rebuilt) or unchanged(candidate)!=unchanged(rebuilt):
        raise ValueError('Independent reconstruction differs from submitted graph')
    diagnostic=inspect(candidate)
    if diagnostic!=proposal['diagnostics']:raise ValueError('Stored diagnostics differ from authoritative validation')
    if identity(assembly)!=base:raise ValueError('Original assembly changed')
    old=inspect(before)
    pass_checks={'original_voltage_defect_present':any(d['code']=='VOLTAGE_INCOMPATIBLE' for d in old['diagnostics']),
        'voltage_defect_removed':not any(d['code']=='VOLTAGE_INCOMPATIBLE' for d in diagnostic['diagnostics']),
        'supported_rules_valid':diagnostic['errors']==0 and diagnostic['supported_rules_status']=='VALID_WITHIN_SUPPORTED_RULES',
        'unknowns_preserved':diagnostic['status']=='UNKNOWN' and diagnostic['unknowns']>0,
        'no_non_wiring_changes':candidate['components']==before['components'],
        'original_assembly_unchanged':identity(assembly)==base}
    return {'status':'PASS' if all(pass_checks.values()) else 'FAIL','checks':pass_checks,'diagnostics':diagnostic,
        'base_sha256':base,'proposed_sha256':identity(candidate),'base_revision':before['revision'],
        'proposed_revision':candidate['revision'],'applied':False,'controller_execution':False,'vm_launches':0,
        'scope':'Independent local schema, graph reconstruction, identity and supported electrical checks in copies only. No physical/electrical safety certification.'}

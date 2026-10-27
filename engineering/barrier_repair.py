"""Physics-aware preflight and bounded, unapplied repairs on Day16 project copies.

The supplied search policy is data-only. Production callbacks below always use
the existing generated-world MuJoCo compiler, simulation and independent replay.
"""
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
import copy,time
import mujoco
import numpy as np
from jsonschema import Draft202012Validator
from physics.contracts import digest
from robustness.contracts import write_once,file_hash
from world.compiler import initial_state
from world.schema import obj
from hardware.advanced import advanced_inspect
from .project import validate,identity
from .created_simulation import compile_created,run
from .actions import execute_copy,CLASSIFICATIONS
from .changes import validate_changeset
from .requirements import PARAMETERS
from .phase17_repair import BarrierParameters,NativeOutcome,preflight,find_verified_repair
from .mujoco_contact_probe import all_initial_contacts,forbidden_initial_contacts

# Exact names from devices.simulation.evaluate. Runtime outcomes must match ALL.
FROZEN_CHECK_NAMES=('opening_deadline','no_closing_on_near_object','closed_after_clear',
                    'no_fault','torque_limit','joint_limits','speed_limit','no_contacts','finite')
BOUNDS=obj({k:PARAMETERS['properties'][k] for k in ('span_m','mass_kg','torque_nm','height_m')})

def _compiled(project):
    p,spec,model,xml,checks=compile_created(project)
    roles=p['creation']['world_roles'];objects={o['id']:o for o in p['world']['objects']}
    support,pivot=objects[roles['support']],objects[roles['pivot']]
    if (support['parent'] is not None or support['geometry']!='box'
        or pivot['parent']!=support['id'] or support['rotation_rad']!=[0,0,0]
        or pivot['rotation_rad']!=[0,0,0] or pivot['position_m'][:2]!=[0,0]):
        raise ValueError('Repair supports the upright generated support and horizontal end-hinged beam only')
    data=initial_state(model,p['world']);mujoco.mj_forward(model,data)
    sg=model.geom('geom_'+roles['support']);pg=model.geom('geom_'+roles['pivot'])
    design=BarrierParameters(spec.mechanical.length_m,spec.mechanical.mass_kg,
        spec.mechanical.torque_limit_nm,float(data.geom_xpos[pg.id,2]),
        objects[roles['beam']]['dimensions_m'][2],float(data.geom_xpos[sg.id,2]+sg.size[2]))
    return p,spec,model,data,checks,design

def preflight_project(project):
    """Read-only static screen; never a dynamic verification or apply result."""
    p,spec,model,data,checks,design=_compiled(project);roles=p['creation']['world_roles']
    names=[model.geom(i).name for i in range(model.ngeom)]
    # The original no_contacts predicate forbids every native contact, including
    # margin contacts. Highlight support pairs without excluding other pairs.
    pairs=list(combinations(names,2))
    witnesses=forbidden_initial_contacts(model,data,pairs,include_margin_contacts=True)
    pf=preflight(design,contact_probe=lambda _:witnesses)
    native_contacts=all_initial_contacts(model,data)
    return {'status':'BLOCKED_PHYSICS_PREFLIGHT' if pf.has_error or pf.has_unknown else 'READY_FOR_NATIVE_PREVIEW',
        'design':asdict(design),'findings':[asdict(f) for f in pf.findings],
        'native':{'model_sha256':checks['compiled']['model_sha256'],'contract_sha256':checks['contract_sha256'],
          'initial_contacts':[{'geom_a':a,'geom_b':b,'signed_distance_m':d} for a,b,d in native_contacts],
          'support_pairs':[['geom_'+roles['support'],'geom_'+roles[k]] for k in ('beam','pivot')],
          'contact_rule':'Original no_contacts requires ncon==0 at every sample; no pair exemptions or masks added.',
          'initial_bias_torque_nm':data.qfrc_bias.tolist()},
        'static_torque_safety_factor':1.2,'dynamic_verification':'NOT_RUN',
        'claim':'Conservative static screen only; native dynamics and all nine unchanged checks remain required.'}

def _operations(original,design):
    _,_,_,_,_,base=_compiled(original);design.validate()
    fixed=('span_m','beam_thickness_m','support_top_m','initial_angle_rad','gravity_m_s2')
    if any(getattr(design,k)!=getattr(base,k) for k in fixed):raise ValueError('Repair may change only mass, authority and pivot height')
    values={'span_m':design.span_m,'mass_kg':design.mass_kg,'torque_nm':design.torque_nm,'height_m':design.pivot_height_m}
    if not Draft202012Validator(BOUNDS).is_valid(values):raise ValueError('Candidate exceeds existing Day16 SI envelope; no expansion permitted')
    objects={o['id']:o for o in original['world']['objects']};roles=original['creation']['world_roles']
    pos=list(objects[roles['pivot']]['position_m']);pos[2]=design.pivot_height_m-objects[roles['support']]['position_m'][2]
    return [{'kind':'set_device_mass','mass_kg':design.mass_kg},
            {'kind':'set_device_actuator_limit','torque_limit_nm':design.torque_nm},
            {'kind':'move_object','target':roles['pivot'],'position_m':pos}]

def _candidate(original,design):
    candidate=validate(execute_copy(original,_operations(original,design)))
    for k in ('id','circuit','controller_sha256','interfaces','creation','design_plans','evidence_refs'):
        if candidate[k]!=original[k]:raise ValueError('Repair changed protected project data: '+k)
    _,old_spec,_,_,_,_=_compiled(original);_,new_spec,_,_,_,_=_compiled(candidate)
    a,b=old_spec.to_dict(),new_spec.to_dict()
    for k in ('mass_kg','torque_limit_nm'):b['mechanical'][k]=a['mechanical'][k]
    if a!=b:raise ValueError('Frozen controller, sensor, environment or acceptance criterion changed')
    return candidate

def _changeset(original,candidate,operations,checks,evidence):
    result={'schema_version':1,'base_project_sha256':identity(original),'base_revision':original['revision'],
      'operations':operations,'dependency_order':list(range(len(operations))),
      'affected_subsystems':sorted({CLASSIFICATIONS[o['kind']]['subsystem'] for o in operations}),
      'preconditions':['Exact populated base project hash/revision; separate explicit human data-application confirmation.',
                       'A changeset against a proposed project cannot be applied to its still-EMPTY authoritative head.'],
      'validation':{'world':'VALID_COMPILED','world_contract_sha256':checks['compiled']['base_world_compilation']['contract_sha256'],
        'electrical':advanced_inspect(candidate['circuit']),'interfaces':'VALID_TYPED_MAPPINGS',
        'simulation':'NOT_RUN; no dynamic expected outcome inferred'},
      'expected_outcomes':['Recorded native evidence: '+str(evidence['new']),
                           'Original evidence: '+str(evidence['old']),
                           'The validation field describes static changeset checks only; recorded dynamics are a separate measured result.'],
      'unknown_consequences':['Finite trusted simulation only; complete electrical/real hardware safety UNKNOWN.',
                              'Visual-only electronics placement is preserved and is not a mechanically modeled mount.'],
      'approval_status':'PROPOSED_NOT_APPLIED','proposed_project':candidate,
      'resulting_project_sha256':identity(candidate),'resulting_revision':candidate['revision'],
      'explanation':'Deterministic bounded repair of measured torque/contact failures. Native evidence passed all nine unchanged requirements; no controller patch or application.',
      'origin':'DEVELOPER_AUTHORED_EVIDENCE_PROPOSAL','model_application_authority':False,'installation_effect':'NONE'}
    return validate_changeset(result)

def propose_repair(project,output,*,max_native_previews=8,max_candidates=100,source_evidence=None,render_image=True):
    """Explicit local operation; no injected physics callback, source, apply or API."""
    if type(max_native_previews) is not int or not 0<=max_native_previews<=8:raise ValueError('At most eight native repair previews')
    if type(max_candidates) is not int or not 1<=max_candidates<=100:raise ValueError('At most 100 static candidates')
    original=validate(project);before=identity(original);_,_,_,_,_,design=_compiled(original)
    out=Path(output);out.mkdir(parents=True,exist_ok=False);started=time.monotonic();runs=[];copies={};preflights={}
    write_once(out/'original_project.json',original);write_once(out/'original_preflight.json',preflight_project(original))
    write_once(out/'scope.json',{'max_native_previews':max_native_previews,'max_candidates':max_candidates,
        'frozen_check_names':FROZEN_CHECK_NAMES,'original_project_sha256':before,'source_evidence':source_evidence,
        'controller_sha256':original['controller_sha256'],'origin':'DETERMINISTIC_LOCAL_REPAIR; not a live model repair',
        'apply_authority':False,'model_requests':0,'vm_launches':0})
    def candidate_for(d):
        if time.monotonic()-started>600:raise ValueError('Bounded local repair window exhausted')
        if d not in copies:copies[d]=_candidate(original,d)
        return copies[d]
    def validate_candidate(d):candidate_for(d)
    def probe(d):
        pf=preflight_project(candidate_for(d));preflights[d]=pf
        # Exact signed native contact records, not visual overlap predictions.
        from .phase17_repair import ContactWitness
        return [ContactWitness(c['geom_a'],c['geom_b'],max(0.,-c['signed_distance_m'])) for c in pf['native']['initial_contacts']]
    def trusted_preview(d):
        candidate=candidate_for(d);folder=out/'runs'/f'{len(runs):03d}';runs.append(folder)
        result=run(candidate,folder,render_image=render_image)
        if tuple(result['acceptance']['checks'])!=FROZEN_CHECK_NAMES:raise ValueError('Frozen nine-check contract changed')
        if result['project']!=candidate or result['base_project_sha256']!=identity(candidate):raise ValueError('Native preview input mismatch')
        if digest(result['samples'])!=result['trajectory_sha256']:raise ValueError('Trajectory identity mismatch')
        return NativeOutcome(result['acceptance']['checks'],result['independent_verification']['status']=='PASS',
            engine='mujoco',evidence_path=str(folder/'result.json'),measured={k:v for k,v in result['acceptance'].items() if type(v) in (int,float)})
    result=find_verified_repair(design,trusted_native_preview=trusted_preview,contact_probe=probe,
        candidate_validator=validate_candidate,frozen_check_names=FROZEN_CHECK_NAMES,
        max_native_previews=max_native_previews,max_candidates=max_candidates)
    write_once(out/'search.json',asdict(result))
    answer={'status':result.state,'original_project_sha256':before,'native_previews':result.native_previews,
        'static_candidates_recorded':len(result.attempts),'proposal_applied':False,'model_requests':0,'vm_launches':0,
        'source_evidence':source_evidence,'evidence_root':str(out),'engineering_changeset':None}
    if result.accepted_candidate is not None:
        d=result.accepted_candidate;candidate=candidate_for(d);_,_,_,_,checks,_=_compiled(candidate)
        accepted=next(a for a in result.attempts if a.accepted);evidence=Path(accepted.native_outcome.evidence_path)
        evidence_link={'old':source_evidence,'new':{'path':str(evidence),'sha256':file_hash(evidence)}}
        changeset=_changeset(original,candidate,_operations(original,d),checks,evidence_link)
        answer.update(engineering_changeset=changeset,accepted_parameters=asdict(d),
            evidence=evidence_link,
            application_status='REQUIRES_SEPARATE_EXPLICIT_HUMAN_REVIEW_AND_COMMIT')
        write_once(out/'engineering_changeset.json',changeset)
    assert identity(original)==before and original==project
    write_once(out/'result.json',answer);return answer

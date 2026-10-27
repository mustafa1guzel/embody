"""Independent deterministic semantic tests; historical model output is immutable."""
import copy,json
from pathlib import Path
import pytest
from engineering.assembly_plan import semantic_preflight,construct,validate_plan,PlanError,PLAN
from engineering.assembly_fixture import fixture_plan
from engineering.assembly_semantics import contract,inventory
from engineering.assembly_live import tools_for,observation,AssemblyTools
from engineering.assembly import AssemblyComposer
from engineering.project import new_project,identity
from ide_api.engineering import EngineeringService
from core.agent.trace import ExecutionTrace
from physics.contracts import digest

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'artifacts/phase18e/20261025'
def historical():return json.loads((HISTORY/'actual_model_plan.json').read_text())['arguments']['plan']
def empty():
 p=new_project();p['world']['environment']['duration_s']=1.;return p
def operations(p,kind):return [o for s in p['steps'] for o in s['operations'] if o['kind']==kind]

def test_all_eight_genuine_wrong_targets_reject_before_any_engine_preview(tmp_path,monkeypatch):
 plan=historical();before=copy.deepcopy(plan);service=EngineeringService(tmp_path/'empty',initial_project=empty());head=service.current()
 def forbidden(*a,**kw):raise AssertionError('Semantic rejection must precede any preview')
 monkeypatch.setattr(service,'preview',forbidden)
 with pytest.raises(PlanError) as failure:construct(service,head,plan)
 d=failure.value.diagnostics
 assert len([x for x in d if x['code']=='WRONG_ID_NAMESPACE' and x['field']=='target'])==8
 assert len([x for x in d if x['code']=='REGISTERED_PROXY_BODY'])==8
 assert len([x for x in d if x['code']=='ROLE_MOUNT_PARENT'])==4
 assert len([x for x in d if x['code']=='DATUM_ROTATION'])==2
 assert len([x for x in d if x['code']=='CHILD_FRAME_MISSING'])==8
 assert service.current()==head and plan==before

def test_legitimate_phase18d_oracle_still_builds_exact_proxy(tmp_path):
 c=AssemblyComposer(EngineeringService(tmp_path/'oracle',initial_project=empty()));head=c.service.current();plan=fixture_plan()
 assert semantic_preflight(head,plan)['status']=='SEMANTIC_PREFLIGHT_PASS'
 q=c.propose(identity(head),0,plan,origin='OFFLINE_PROTOCOL_FIXTURE')
 assert len(q['proposed_project']['shape_specs'])==9 and q['construction']['total_actions']==71
 assert c.reconstruct(q)[0]==q['proposed_project'] and c.service.current()==head
 original=json.loads((HISTORY/'offline_project_proposal.json').read_text())
 assert q['proposed_project']==original['proposed_project']
 assert q['structural']['compiled']==original['structural']['compiled']

@pytest.mark.parametrize('case,code',[
 ('part_target_is_body','WRONG_ID_NAMESPACE'),('body_target_is_part','WRONG_ID_NAMESPACE'),
 ('wrong_mount_parent','MOUNT_PARENT'),('protected_id','ROVER_DATUM_ALIAS'),
 ('protected_rotation','PROTECTED_DATUM'),('protected_source','PROTECTED_DATUM'),
 ('unsupported_family_datum','UNSUPPORTED_DATUM'),('child_frame_from_parent','CHILD_FRAME_MISSING'),
 ('wheel_local_frame','WHEEL_LOCAL_DATUM'),('wrong_joint_axis','JOINT_REQUIRED'),
 ('fixed_mount_has_joint','FIXED_MOUNT_REQUIRED'),('attachment_wrong_parent','ATTACHMENT_PARENT'),
 ('missing_body','MISSING_REFERENCE'),('undeclared_dependency','UNDECLARED_DEPENDENCY')])
def test_isolated_semantic_failure_classes(case,code):
 p=fixture_plan();frames=operations(p,'set_attachment_frame');fixed=operations(p,'attach_part_to_mount');joints=operations(p,'attach_part_to_joint')
 if case=='part_target_is_body':frames[0]['target']='chassis'
 elif case=='body_target_is_part':next(o for o in operations(p,'set_mass') if o['target']=='front_axle_mount')['target']='shape_chassis'
 elif case=='wrong_mount_parent':next(o for o in operations(p,'create_object') if o['id']==frames[0]['mounted_body_id'])['parent']='rover_root'
 elif case=='protected_id':frames[0]['frame']['id']='renamed'
 elif case=='protected_rotation':frames[0]['frame']['rotation_rad']=[0,0,0]
 elif case=='protected_source':frames[0]['frame']['source']='origin'
 elif case=='unsupported_family_datum':frames[0]['frame']={'id':'custom','source':'axle_left','hole_id':None,'rotation_rad':[0,0,0]}
 elif case=='child_frame_from_parent':fixed[0]['frame_id']='front_axle'
 elif case=='wheel_local_frame':joints[0]['frame_id']='origin'
 elif case=='wrong_joint_axis':next(o for o in operations(p,'create_joint') if o['target']==joints[0]['joint_body_id'])['joint']['axis']=[1,0,0]
 elif case=='fixed_mount_has_joint':next(o for o in operations(p,'create_joint') if o['target']==fixed[0]['mount_body_id'])['joint']={'kind':'revolute','axis':[0,0,1],'range':[-1,1],'initial_position':0,'initial_velocity':0,'damping':0}
 elif case=='attachment_wrong_parent':fixed[0]['mount_body_id']='rover_root'
 elif case=='missing_body':frames[0]['mounted_body_id']='missing'
 else:p['steps'][1]['depends_on']=[]
 snapshot=copy.deepcopy(p);r=semantic_preflight(empty(),p)
 assert code in [d['code'] for d in r['diagnostics']],r
 assert p==snapshot and r['new_native_steps']==0

def test_semantic_pass_never_replaces_actual_geometry_validation(tmp_path):
 p=fixture_plan();wheel=next(o['part'] for o in operations(p,'create_parametric_part') if o['part']['family']=='wheel');wheel['parameters']['axle_hole_diameter_m']=.04
 assert semantic_preflight(empty(),p)['status']=='SEMANTIC_PREFLIGHT_PASS'
 s=EngineeringService(tmp_path/'invalid_geometry',initial_project=empty());head=s.current()
 with pytest.raises(ValueError):construct(s,head,p)
 assert s.current()==head

def test_inspection_exposes_namespaces_protected_datums_and_actual_inventory(tmp_path):
 c=AssemblyComposer(EngineeringService(tmp_path/'actual',initial_project=empty()));con=observation(c)['identity_and_attachment_contract']
 assert len(con['current_inventory']['bodies'])==1 and con['current_inventory']['parts']==[]
 assert 'no separate' in con['identifier_namespaces']['joint_body_id'].lower()
 assert next(f for f in con['protected_datums']['chassis'] if f['id']=='front_axle')['rotation_rad'][0]>1.5
 q=c.propose(identity(c.service.current()),0,fixture_plan());inv=inventory(q['proposed_project'])
 assert len(inv['parts'])==9 and len(inv['bodies'])==19
 assert next(p for p in inv['parts'] if p['part_id']=='shape_chassis')['registered_children']
 text=json.dumps(tools_for(1))
 assert 'OWNER part target' in text and 'CHILD part target' in text and 'Local to the TARGET ShapeSpec' in text

def test_historical_rejection_bootstrap_explains_without_rewriting_history():
 root=HISTORY/'live_project';files={p:p.read_bytes() for p in root.rglob('*.json')};c=AssemblyComposer(EngineeringService(root))
 b=c.bootstrap();r=b['rejections'][0]
 assert r['original']['error']['message']=='Missing or forward construction reference: part:front_axle_mount'
 assert r['original']['plan']==historical() and r['current_analysis']['errors']==34
 assert b['review']['proposal'] is None and not b['application_allowed']
 assert all(p.read_bytes()==raw for p,raw in files.items()) and c.service.current()['revision']==0

def test_dispatch_preserves_structured_failure_for_future_receipts(tmp_path):
 c=AssemblyComposer(EngineeringService(tmp_path/'protocol',initial_project=empty()));trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='deterministic_mock');t=AssemblyTools(c,trace)
 assert t.dispatch('inspect_assembly_capabilities',{})['ok']
 r=t.dispatch('propose_assembly_plan',{'expected_sha256':identity(c.service.current()),'expected_revision':0,'plan':historical()})
 assert not r['ok'] and r['error']['diagnostics'] and t.result==r and not t.schemas
 assert c.service.current()['revision']==0 and not list(c.proposals.root.glob('*.json'))

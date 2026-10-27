"""Deterministic reliability/negative tests. No real model transport or VM."""
import copy,json,math
from pathlib import Path
import pytest
from engineering.assembly import AssemblyComposer
from engineering.assembly_examples import rover_plan
from engineering.assembly_plan import validate_plan,PlanError
from engineering.assembly_revision import AssemblyRevisionTools
from engineering.project import new_project,identity
from engineering.actions import execute_copy
from ide_api.engineering import EngineeringService
from core.agent.trace import ExecutionTrace
from tools.security_baseline_review import validate_migration,OLD_REQ,NEW_REQ
ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def c(tmp_path):
 p=new_project();p['world']['environment']['duration_s']=1.;return AssemblyComposer(EngineeringService(tmp_path/'project',initial_project=p))
def ops(p,k):return [o for s in p['steps'] for o in s['operations'] if o['kind']==k]
def assessment(c,p):return c.assess(identity(c.service.current()),0,p)

def test_safe_root_uses_existing_defaults_and_explicit_mass_only(c):
 p=c.service.current();op=rover_plan()['steps'][0]['operations'][0];after=execute_copy(p,[op]);root=next(o for o in after['world']['objects'] if o['id']==op['id'])
 assert root['joint']=={'kind':'free','axis':[0.,0.,1.],'range':[-1,1],'initial_position':0.,'initial_velocity':0.,'damping':0.}
 assert root['mass_kg']==.01 and root['dimensions_m']==[.006]*3 and root['parent'] is None
 assert c.service.current()==p

@pytest.mark.parametrize('field,value',[('joint',{'range':[0,0]}),('parent','floor'),('mass_kg',0),('mass_kg',True),('mass_kg',2.1),('dimensions_m',[0,.01,.01]),('dimensions_m',[.7,.01,.01])])
def test_safe_root_rejects_low_level_or_out_of_bounds_fields(c,field,value):
 p=rover_plan();p['steps'][0]['operations'][0][field]=value
 r=assessment(c,p);assert r['status']=='REJECTED' and r['diagnostics'];assert c.service.current()['revision']==0

@pytest.mark.parametrize('phase,path,mass,codes',[
 ('18E','artifacts/phase18e/20261025/actual_model_plan.json',2.39,{'WRONG_ID_NAMESPACE','REVOLUTE_RANGE','TOTAL_MASS'}),
 ('18E.1','artifacts/phase18e_1/20261025/actual_live_model_plan.json',2.45,{'JOINT_RANGE','FREE_ROOT_CONTRACT','TOTAL_MASS'})])
def test_entire_historical_plans_are_audited_without_translation(c,phase,path,mass,codes):
 raw=(ROOT/path).read_bytes();p=json.loads(raw)['arguments']['plan'];snapshot=copy.deepcopy(p);r=assessment(c,p)
 assert r['status']=='REJECTED' and r['total_mass_kg']==pytest.approx(mass)
 assert codes<={d['code'] for d in r['diagnostics']}
 with pytest.raises(ValueError):c.propose(identity(c.service.current()),0,p)
 assert p==snapshot and (ROOT/path).read_bytes()==raw and c.service.current()['revision']==0

@pytest.mark.parametrize('mode,code',[
 ('equal_range','JOINT_RANGE'),('initial_outside','JOINT_RANGE'),('over_pi','REVOLUTE_RANGE'),('axis','JOINT_AXIS'),
 ('mass','TOTAL_MASS'),('overcommand','ACTUATOR_CONTRACT'),('authority','ROVER_ACTUATOR'),('zero_command','ROVER_ACTUATOR'),('unit','ACTUATOR_CONTRACT'),('front_motor','FRONT_PASSIVE'),
 ('parent','MOUNT_PARENT'),('namespace','WRONG_ID_NAMESPACE'),('bore','COMPILED_CONSTRUCTION'),('radius','SHAPE_GEOMETRY')])
def test_independent_failure_classes_still_reject(c,mode,code):
 p=rover_plan();j=next(o for o in ops(p,'create_joint') if o['joint']);a=ops(p,'set_actuator')[0]
 if mode=='equal_range':j['joint']['range']=[0,0]
 elif mode=='initial_outside':j['joint']['initial_position']=2.;j['joint']['range']=[-1,1]
 elif mode=='over_pi':j['joint']['range']=[-math.pi,3.1416]
 elif mode=='axis':j['joint']['axis']=[1,1,0]
 elif mode=='mass':ops(p,'create_free_root')[0]['mass_kg']=2
 elif mode=='overcommand':a['actuator']['command']=.03
 elif mode=='authority':a['actuator']['limit']=.09
 elif mode=='zero_command':a['actuator']['command']=0
 elif mode=='unit':a['actuator']['unit']='N'
 elif mode=='front_motor':p['steps'][2]['operations'].append({'kind':'set_actuator','target':p['roles']['wheels']['front_left']['joint_body_id'],'actuator':{'limit':.02,'command':.001,'unit':'N*m'}})
 elif mode=='parent':ops(p,'create_object')[0]['parent']=p['roles']['root_body_id']
 elif mode=='namespace':ops(p,'set_attachment_frame')[0]['target']=p['roles']['chassis_part_id']+'_body'
 elif mode=='bore':next(o['part'] for o in ops(p,'create_parametric_part') if o['part']['family']=='wheel')['parameters']['axle_hole_diameter_m']=.015
 elif mode=='radius':ops(p,'create_parametric_part')[0]['part']['parameters']['corner_radius_m']=.09
 head=c.service.current();r=assessment(c,p);assert code in [d['code'] for d in r['diagnostics']],r
 assert r['status']=='REJECTED' and r['native']=='NOT_EXECUTED' and c.service.current()==head
 with pytest.raises(ValueError):c.propose(identity(head),0,p)

def test_new_independent_rover_is_compiled_without_implicit_dynamic_pass(c):
 p=rover_plan();head=c.service.current();r=assessment(c,p)
 assert r['status']=='COMPILED_REVIEW_READY' and r['total_mass_kg']==pytest.approx(.292)
 assert not any(b['source']=='EXISTING_PRIMITIVE_DEFAULT' and b['mass_kg'] for b in r['mass_allocation'])
 assert r['physical_status']=='PENDING_EXPLICIT_NATIVE_PREVIEW_AND_REPLAY' and r['new_native_steps']==0
 q=c.propose(identity(head),0,p);assert c.reconstruct(q)[0]==q['proposed_project'] and c.service.current()==head

def test_bounded_revision_is_author_supplied_linked_and_never_automatically_applied(c,tmp_path):
 t=AssemblyRevisionTools(c,ExecutionTrace(tmp_path/'trace.jsonl',model_mode='EXPLICIT_DETERMINISTIC_PROTOCOL_TEST'))
 assert t.dispatch('inspect_assembly_capabilities',{})['ok'];bad=rover_plan();bad['steps'][0]['operations'][0]['mass_kg']=2
 first=t.dispatch('propose_assembly_plan',{'expected_sha256':identity(c.service.current()),'expected_revision':0,'revision_of':None,'plan':bad});assert not first['ok'] and first['assessment']['diagnostics']
 supplied=rover_plan(label='newauthor');result=t.dispatch('propose_assembly_plan',{'expected_sha256':identity(c.service.current()),'expected_revision':0,'revision_of':first['failure_id'],'plan':supplied})
 assert result['ok'] and result['result']['assembly_plan']==supplied and result['revision_of']==first['failure_id']
 assert not t.schemas and c.service.current()['revision']==0
 assert not t.dispatch('propose_assembly_plan',{})['ok']

def test_unlinked_or_excess_revisions_stop(c,tmp_path):
 t=AssemblyRevisionTools(c,ExecutionTrace(tmp_path/'trace.jsonl',model_mode='EXPLICIT_DETERMINISTIC_PROTOCOL_TEST'));t.dispatch('inspect_assembly_capabilities',{})
 r=t.dispatch('propose_assembly_plan',{'expected_sha256':identity(c.service.current()),'expected_revision':0,'revision_of':'a'*64,'plan':rover_plan()})
 assert not r['ok'] and not t.schemas and not list(c.proposals.root.glob('*.json'))

def test_migration_review_cannot_accept_any_other_protected_delta():
 old={'requirements.txt':OLD_REQ,'robot/controller.py':'a'*64};new={**old,'requirements.txt':NEW_REQ}
 assert validate_migration(old,new)['status']=='EXACT_ONE_FILE_MIGRATION'
 for bad in [{**new,'robot/controller.py':'b'*64},{**new,'extra':'c'*64},{**old,'requirements.txt':'d'*64},old]:
  with pytest.raises(ValueError):validate_migration(old,bad)

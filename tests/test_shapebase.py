"""Authoritative shape schema, real proxy compilation and review transactions."""
import copy,json
import pytest
import mujoco
import numpy as np
from shapebase.model import create_shape,validate_shape,validate_project_shapes,dimensions
from shapebase.geometry import generate
from shapebase.examples import create_disposable_arm,part_input
from engineering.actions import execute_copy,check_operations
from engineering.project import new_project,validate,identity
from engineering.agent import EngineeringTools
from core.agent.trace import ExecutionTrace
from world.compiler import compile_world,initial_state
from world.simulation import run,verify

@pytest.fixture
def arm(tmp_path):return create_disposable_arm(tmp_path/'independent_arm')[0]

def edit(length=.42):return [{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':length}]

def test_length_regeneration_preserves_identity_holes_frames_and_moves_declared_elbow(arm):
 before=arm.current();p=arm.propose(identity(before),4,edit(),'Review length change');after=p['proposed_project']
 assert arm.current()==before and p['approval_status']=='PROPOSED_NOT_APPLIED'
 a,b=before['shape_specs'][0],after['shape_specs'][0];ga,gb=generate(a),generate(b)
 assert a['id']==b['id'] and a['body_id']==b['body_id'] and b['geometry_revision']==a['geometry_revision']+1
 assert [h['id'] for h in ga['holes']]==[h['id'] for h in gb['holes']]==['mount_a','mount_b']
 assert gb['holes'][0]['center_m'][0]==pytest.approx(-.1344) and ga['holes'][0]['center_m'][0]==pytest.approx(-.096)
 assert a['joint_attachment']==b['joint_attachment'] and a['mounted_bodies']==b['mounted_bodies']
 elbow=next(o for o in after['world']['objects'] if o['id']=='elbow');assert elbow['position_m']==gb['attachment_frames'][2]['position_m']
 validate(after)
 with pytest.raises(ValueError,match='approval'):arm.decide(identity(before),4,p['proposal_id'],'apply','')
 applied=arm.decide(identity(before),4,p['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
 assert applied['project']==after
 with pytest.raises(ValueError,match='Stale'):arm.propose(identity(before),4,edit(),'Stale')

@pytest.mark.parametrize('op',[
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':float('nan')},
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':0},
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':True},
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':float('inf')},
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'width_m','value':.5},
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'end_radius_m','value':.1},
 {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'diameter_m','value':.05},
 {'kind':'update_mounting_hole','target':'shape_link_one','hole':{'id':'mount_a','diameter_m':.02,'u':.49,'v':.49}},
 {'kind':'update_mounting_hole','target':'shape_link_one','hole':{'id':'mount_a','diameter_m':.012,'u':.32,'v':0}},
 {'kind':'add_mounting_hole','target':'shape_link_one','hole':{'id':'mount_a','diameter_m':.01,'u':0,'v':0}},
 {'kind':'attach_part_to_joint','target':'shape_link_one','joint_body_id':'missing','frame_id':'mount_a'},
 {'kind':'attach_part_to_joint','target':'shape_link_one','joint_body_id':'elbow','frame_id':'mount_a'},
 {'kind':'attach_part_to_joint','target':'shape_link_one','joint_body_id':'shoulder','frame_id':'missing'},
 {'kind':'set_attachment_frame','target':'shape_link_one','frame':{'id':'bad','source':'hole','hole_id':'absent','rotation_rad':[0,0,0]},'mounted_body_id':None},
 {'kind':'set_attachment_frame','target':'shape_link_one','frame':{'id':'bad','source':'origin','hole_id':None,'rotation_rad':[1,0,0]},'mounted_body_id':None},
 {'kind':'set_attachment_frame','target':'shape_link_one','frame':{'id':'bad','source':'origin','hole_id':None,'rotation_rad':[0,0,0]},'mounted_body_id':'shoulder'},
 {'op':'resize_link','length':.42},
 {'kind':'boolean_cut','source':'anything'},
])
def test_invalid_proposals_fail_atomically(arm,op):
 before=arm.current()
 with pytest.raises((ValueError,TypeError)):arm.propose(identity(before),4,[op],'Invalid shape input')
 assert arm.current()==before


def test_direct_shape_edits_and_generic_proxy_bypasses_rejected(arm):
 before=arm.current()
 with pytest.raises(ValueError,match='review'):arm.edit(identity(before),4,edit())
 for op in ({'kind':'set_geometry','target':'link_one','dimensions_m':[.5,.06,.015]},{'kind':'move_object','target':'elbow','position_m':[.4,0,0]}):
  with pytest.raises(ValueError):arm.propose(identity(before),4,[op],'Cannot bypass shape ownership')
 assert arm.current()==before


def test_reject_and_tampered_proposal_do_not_apply(arm):
 before=arm.current();p=arm.propose(identity(before),4,edit(),'Reject test')
 arm.decide(identity(before),4,p['proposal_id'],'reject','REJECT ENGINEERING CHANGE');assert arm.current()==before
 with pytest.raises(ValueError,match='already decided'):arm.decide(identity(before),4,p['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
 q=copy.deepcopy(p);q.pop('proposal_id');q['validation']['shapes']['source_sha256']={};key=arm.proposals.put(q)
 with pytest.raises(ValueError,match='source identity'):arm.decide(identity(before),4,key,'apply','APPLY REVIEWED ENGINEERING CHANGE')
 assert arm.current()==before


def test_add_hole_and_configure_frame_are_actual_geometry_features(arm):
 p=arm.current();ops=[{'kind':'add_mounting_hole','target':'shape_link_one','hole':{'id':'extra','diameter_m':.008,'u':0,'v':0}},{'kind':'set_attachment_frame','target':'shape_link_one','frame':{'id':'tool_mount','source':'hole','hole_id':'extra','rotation_rad':[0,0,.2]},'mounted_body_id':None}]
 q=arm.propose(identity(p),4,ops,'Add a bounded feature');g=q['validation']['shapes']['parts'][0]['geometry']
 assert len(g['holes'])==3 and next(f for f in g['attachment_frames'] if f['id']=='tool_mount')['position_m']==[0,0,0]
 assert len(g['sections'][0]['outline_m'])>=32

@pytest.mark.parametrize('family,parameters',[
 ('rounded_link',{'length_m':.3,'width_m':.06,'thickness_m':.015,'end_radius_m':.03}),
 ('drilled_plate',{'length_m':.12,'width_m':.08,'thickness_m':.01,'corner_radius_m':.01}),
 ('motor_bracket',{'length_m':.12,'width_m':.08,'height_m':.06,'thickness_m':.01}),
 ('shaft',{'length_m':.1,'diameter_m':.02}),
 ('structural_support',{'length_m':.08,'width_m':.06,'height_m':.15}),
])
def test_all_families_compile_real_native_proxies_with_honest_physics(family,parameters):
 holes=part_input('s','b',None)['mounting_holes'] if family=='rounded_link' else []
 data={'id':'shape_test','body_id':'proxy','family':family,'parameters':parameters,'parent_body_id':None,'position_m':[0,0,.3],'rotation_rad':[0,0,.2],'mass_kg':0,'mounting_holes':holes}
 p=validate(execute_copy(new_project(),[{'kind':'create_parametric_part','part':data}]))
 spec=p['shape_specs'][0];g=generate(spec);model,xml,proof=compile_world(p['world']);native=model.geom('geom_proxy')
 assert len(g['sections'])==(2 if family=='motor_bracket' else 0 if family=='shaft' else 1)
 expected=dimensions(spec);np.testing.assert_allclose(native.size[:2] if family=='shaft' else native.size,[expected[0]/2,expected[2]/2] if family=='shaft' else np.array(expected)/2)
 assert spec['physical']['density_source']=='UNKNOWN_NOT_INFERRED'
 assert spec['physical']['accuracy']==('EXACT_SUPPORTED_PRIMITIVE' if family in ('shaft','structural_support') else 'APPROXIMATE')


def test_native_length_changes_inertia_and_joint_anchor_and_replays_independently(arm):
 before=arm.current();after=arm.propose(identity(before),4,edit(),'Native check')['proposed_project']
 old,_,_=compile_world(before['world']);new,_,proof=compile_world(after['world']);data=initial_state(new,after['world']);mujoco.mj_forward(new,data)
 assert new.nv==new.nu==2
 assert new.body('link_one').mass[0]==pytest.approx(.15)
 assert max(new.body('link_one').inertia)>max(old.body('link_one').inertia)
 np.testing.assert_allclose(data.xanchor[new.joint('joint_elbow').id],[.2688,0,.175],atol=1e-12)
 result=run(after['world']);assert result['independent_verification']['status']=='PASS' and verify(result)['status']=='PASS'
 assert result['samples'][0]['qpos']!=result['samples'][-1]['qpos']
 assert len(proof['force_probes'])==6 and arm.current()==before


def test_native_proposal_preview_keeps_head_unchanged_and_bounds_repeats(arm):
 before=arm.current();p=arm.propose(identity(before),4,edit(),'Explicit native preview')
 r=arm.preview_shapes(identity(before),4,p['proposal_id']);assert r['status']=='NATIVE_PROXY_REPLAY_PASS'
 assert r['result']['independent_verification']['status']=='PASS' and arm.current()==before
 arm.preview_shapes(identity(before),4,p['proposal_id'])
 with pytest.raises(ValueError,match='Two native'):arm.preview_shapes(identity(before),4,p['proposal_id'])
 assert arm.current()==before


def test_machine_readable_tools_propose_shapes_but_cannot_apply(arm,tmp_path):
 before=arm.current();trace=ExecutionTrace(tmp_path/'trace',model_mode='deterministic-protocol-test');tools=EngineeringTools(arm,trace)
 r=tools.dispatch('propose_engineering_change',{'expected_sha256':identity(before),'expected_revision':4,'operations':edit(),'explanation':'Deterministic protocol test; not live AI'})
 assert r['ok'] and r['result']['affected_subsystems']==['shapes'] and arm.current()==before
 assert not tools.dispatch('apply_shape',{})['ok']


def test_legacy_project_identity_and_original_generated_project_are_preserved():
 from pathlib import Path
 from core.simulation import ROOT
 from robustness.contracts import file_hash
 p=Path(ROOT/'artifacts/phase17_live_creation/20261024/live_execution/review_registry/projects/p_192ae155384543e2b4636b4b8c396768')
 head=json.loads((p/'head.json').read_text());original=json.loads((p/'projects'/(head['sha256']+'.json')).read_text());assert identity(original)==head['sha256'] and original['revision']==0
 assert 'shape_specs' not in validate(new_project())
 with pytest.raises(ValueError,match='independent'):execute_copy(original,[{'kind':'create_parametric_part','part':part_input('no','not_allowed',None)}])
 assert file_hash(p/'head.json')=='29831a9ad280659b5cfc9c5b60f78f58016c689864c62f1fe790a5c69b525936'


def test_coupled_dimension_edits_validate_final_batch_atomically(arm):
    before=arm.current();operations=[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'end_radius_m','value':.04},{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'width_m','value':.08}]
    proposal=arm.propose(identity(before),4,operations,'Coordinated radius and width')
    assert proposal['proposed_project']['shape_specs'][0]['parameters']['width_m']==.08
    assert arm.current()==before


def test_false_physics_claim_and_non_z_joint_are_rejected(arm):
    before=arm.current();false=copy.deepcopy(before);false['shape_specs'][0]['physical']['accuracy']='EXACT_SUPPORTED_PRIMITIVE'
    with pytest.raises(ValueError,match='Physical representation'):validate(false)
    bad=copy.deepcopy(before);next(o for o in bad['world']['objects'] if o['id']=='shoulder')['joint']['axis']=[0,1,0]
    with pytest.raises(ValueError,match='revolute'):validate(bad)

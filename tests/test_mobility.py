"""Actual geometry, typed transactions and native mobility proxy checks."""
import copy,math
from pathlib import Path
import pytest
import mujoco
import numpy as np
from shapebase.mobility_examples import create_example,part
from shapebase.model import create_shape,validate_shape,validate_project_shapes
from shapebase.mobility import PARAMETERS
from shapebase.geometry import generate
from engineering.project import identity
from world.compiler import compile_world,initial_state

DEFAULTS={
 'wheel':{'outer_diameter_m':.12,'thickness_m':.025,'axle_hole_diameter_m':.009,'hub_thickness_m':.004},
 'axle':{'diameter_m':.008,'length_m':.24},
 'chassis':{'length_m':.3,'width_m':.18,'thickness_m':.015,'corner_radius_m':.012},
 'motor_mount':{'length_m':.045,'width_m':.03,'thickness_m':.006,'corner_radius_m':.004},
 'drone_arm':{'length_m':.2,'width_m':.025,'thickness_m':.008},
 'motor_pad':{'length_m':.05,'width_m':.05,'thickness_m':.006,'corner_radius_m':.008},
}
@pytest.fixture(scope='module')
def examples(tmp_path_factory):
 root=tmp_path_factory.mktemp('mobility').resolve()
 return {kind:create_example(root/kind,kind) for kind in ('rover','drone')}

@pytest.mark.parametrize('family',list(DEFAULTS))
def test_new_families_have_bounded_generated_geometry_and_real_datums(family):
 s=create_shape(part('sample',family,DEFAULTS[family],None),'engineering_project');g=generate(s)
 assert g['shape_id']==s['id'] and g['body_id']=='sample'
 assert all(v>0 for v in g['dimensions_m']) and len(g['attachment_frames'])<=20
 assert s['physical']['density_source']=='UNKNOWN_NOT_INFERRED'
 if family=='wheel':
  assert [x['id'] for x in g['sections']]==['tire','hub'] and g['holes'][0]['id']=='axle_hole'
  assert g['physical']['accuracy']=='APPROXIMATE' and g['physical']['representation']=='SOLID_CYLINDER'
 if family=='axle':assert g['cylinder']['length_m']==.24 and {'axle_left','axle_right'}<={f['id'] for f in g['attachment_frames']}

@pytest.mark.parametrize('family,parameter,value',[(f,k,value) for f,p in DEFAULTS.items() for k in p for value in (float('nan'),True,-1)])
def test_nonfinite_bool_and_negative_parameters_reject(family,parameter,value):
 data=part('bad',family,DEFAULTS[family],None);data['parameters'][parameter]=value
 with pytest.raises(ValueError):create_shape(data,'engineering_project')

@pytest.mark.parametrize('parameters',[
 {'outer_diameter_m':.03,'thickness_m':.02,'axle_hole_diameter_m':.029,'hub_thickness_m':0},
 {'outer_diameter_m':.12,'thickness_m':.02,'axle_hole_diameter_m':.009,'hub_thickness_m':.2},
])
def test_invalid_wheel_wall_and_hub_bounds(parameters):
 with pytest.raises(ValueError):create_shape(part('bad','wheel',parameters,None),'engineering_project')

@pytest.mark.parametrize('kind',['rover','drone'])
def test_reviewed_assembly_and_parameter_edit_preserve_head_and_identities(examples,kind):
 s,r=examples[kind];before=s.current();q=r['edit_proposal'];after=q['proposed_project']
 assert s.current()==r['base']==before and q['approval_status']=='PROPOSED_NOT_APPLIED'
 assert {p['id'] for p in before['shape_specs']}=={p['id'] for p in after['shape_specs']}
 validate_project_shapes(before);validate_project_shapes(after)
 for a,b in zip(before['shape_specs'],after['shape_specs'],strict=True):
  assert a['body_id']==b['body_id'] and a['attachment_frames']==b['attachment_frames'] and a['mounted_bodies']==b['mounted_bodies']
 if kind=='drone':
  assert len(q['operations'])==4
  m,_,_=compile_world(after['world']);d=initial_state(m,after['world']);mujoco.mj_forward(m,d)
  points=[d.xpos[m.body('pad_'+k).id].copy() for k in ('east','north','west','south')]
  np.testing.assert_allclose(np.array(points)[:,:2],[[.31,0],[0,.31],[-.31,0],[0,-.31]],atol=1e-12)
  assert m.nv==m.nu==0
 else:
  m,_,c=compile_world(after['world']);assert m.nv==10 and m.nu==2 and len(c['force_probes'])==6
  wheel=next(x for x in c['compiled'] if x['id']=='front_left_wheel')
  assert wheel['mass_kg']==pytest.approx(.03) and wheel['size_mujoco'][:2]==pytest.approx([.072,.0145])
 with pytest.raises(ValueError,match='approval'):s.decide(identity(before),before['revision'],q['proposal_id'],'apply','')
 assert s.current()==before

@pytest.mark.parametrize('kind',['rover','drone'])
def test_real_native_preview_and_fresh_replay_never_apply(examples,kind):
 s,r=examples[kind];before=s.current();q=r['edit_proposal'];n=s.preview_shapes(identity(before),before['revision'],q['proposal_id'])
 assert n['status']=='NATIVE_PROXY_REPLAY_PASS' and n['result']['independent_verification']['status']=='PASS'
 assert len(n['result']['samples'])==201 and s.current()==before
 if kind=='rover':assert n['result']['samples'][0]['qpos']!=n['result']['samples'][-1]['qpos']
 else:assert all(x['qpos']==[] for x in n['result']['samples'])

@pytest.mark.parametrize('change',[
 {'kind':'update_shape_parameter','target':'shape_rear_axle','parameter':'diameter_m','value':.012},
 {'kind':'update_shape_parameter','target':'shape_front_left_wheel','parameter':'axle_hole_diameter_m','value':.02},
 {'kind':'attach_part_to_mount','target':'shape_front_left_wheel','mount_body_id':'front_axle','frame_id':'axle'},
 {'kind':'set_attachment_frame','target':'shape_chassis','frame':{'id':'front_axle','source':'front_axle','hole_id':None,'rotation_rad':[0,0,0]},'mounted_body_id':'front_axle_mount'},
 {'kind':'set_attachment_frame','target':'shape_chassis','frame':{'id':'bad','source':'motor_pad','hole_id':None,'rotation_rad':[0,0,0]},'mounted_body_id':None},
 {'kind':'move_object','target':'front_axle_mount','position_m':[0,0,1]},
])
def test_invalid_support_clearance_datum_and_bypass_reject_atomically(examples,change):
 s,_=examples['rover'];before=s.current()
 with pytest.raises(ValueError):s.propose(identity(before),before['revision'],[change],'Invalid negative test')
 assert s.current()==before


def test_conflicting_fixed_joint_and_duplicate_mounts_reject(examples):
 s,r=examples['drone'];before=s.current()
 with pytest.raises(ValueError):s.propose(identity(before),before['revision'],[{'kind':'attach_part_to_joint','target':'shape_arm_east','joint_body_id':'arm_east_root','frame_id':'root'}],'Cannot replace fixed mount with a fictitious joint')
 bad=copy.deepcopy(before);bad['shape_specs'][0]['mounted_bodies'].append(copy.deepcopy(bad['shape_specs'][0]['mounted_bodies'][0]))
 with pytest.raises(ValueError):validate_project_shapes(bad)
 assert s.current()==before


def test_zero_extra_hub_is_supported_but_zero_legacy_dimensions_remain_rejected(examples):
 s,r=examples['rover'];before=s.current()
 ops=[{'kind':'update_shape_parameter','target':'shape_front_left_wheel','parameter':'hub_thickness_m','value':0}]
 q=s.propose(identity(before),before['revision'],ops,'Optional extra hub off, no application')
 wheel=next(p for p in q['validation']['shapes']['parts'] if p['spec']['body_id']=='front_left_wheel')
 assert wheel['geometry']['dimensions_m'][2]==.025 and len(wheel['geometry']['sections'])==2
 with pytest.raises(ValueError):s.propose(identity(before),before['revision'],[{'kind':'update_shape_parameter','target':'shape_chassis','parameter':'thickness_m','value':0}],'Invalid zero thickness')
 assert s.current()==before


def test_mobility_reserved_datums_and_unknown_parameters_cannot_be_forged():
 data=part('bad','drone_arm',DEFAULTS['drone_arm'],None);data['parameters']['lift_newtons']=2
 with pytest.raises(ValueError):create_shape(data,'engineering_project')
 s=create_shape(part('arm','drone_arm',DEFAULTS['drone_arm'],None),'engineering_project')
 s['attachment_frames']=[f for f in s['attachment_frames'] if f['id']!='motor_pad']
 with pytest.raises(ValueError,match='stable mobility datum'):validate_shape(s)


def test_rover_wheel_native_axis_is_horizontal_and_construction_never_calls_apply(examples):
 from ide_api.engineering import EngineeringService
 s,r=examples['rover'];m,_,_=compile_world(s.current()['world']);d=initial_state(m,s.current()['world']);mujoco.mj_forward(m,d)
 for name in ('front_axle','rear_axle','front_left_wheel','rear_right_wheel'):
  gid=m.geom('geom_'+name).id
  np.testing.assert_allclose(d.geom_xmat[gid].reshape(3,3)[:,2],[0,-1,0],atol=1e-12)
 assert r['setup_apply_calls']==0 and r['construction_review_head_revision']==0
 empty=EngineeringService(s.root/'construction_review').current()
 assert empty['revision']==0 and not empty.get('shape_specs')
 assert all(step['application'].startswith('NO_APPLY_CALL') for step in r['setup_receipts'])

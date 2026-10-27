"""New real restricted-scene compilation and measured physics; no candidate code."""
import copy,json,hashlib
import numpy as np
import pytest
from world.objects import primitive,LIBRARY,empty_world
from world.schema import validate,identity
from world.compiler import compile_world
from world.simulation import run,verify
from world.persistence import Store,envelope,load
from world.examples import obstacle,motor,assembly

@pytest.mark.parametrize('kind',LIBRARY)
def test_native_primitive_defaults_are_serializable_and_deterministically_compiled(kind):
    w=empty_world();w['objects'].append(primitive(kind,'supported'))
    a=compile_world(w);b=compile_world(json.loads(json.dumps(w)))
    assert a[1:]==b[1:] and a[2]['contract']['world_sha256']==identity(w)
    assert a[0].geom('geom_supported').id>=0


def test_world_edited_obstacle_changes_real_contacts_and_measured_motion(tmp_path):
    before=run(obstacle(),tmp_path/'before');after=run(obstacle(1.2),tmp_path/'after')
    contact=lambda r:next(s['time_s'] for s in r['samples'] if s['contacts'])
    assert contact(after)-contact(before)>.35
    assert after['samples'][-1]['qpos'][0]-before['samples'][-1]['qpos'][0]>.35
    assert before['world_sha256']!=after['world_sha256'] and before['contract_sha256']!=after['contract_sha256']
    bad=copy.deepcopy(before);bad['samples'][-1]['qpos'][0]+=.01
    with pytest.raises(ValueError):verify(bad)


def test_mass_inertia_actuator_and_initial_state_are_native_not_labels():
    old=compile_world(motor());new=compile_world(motor(.2,.04));assert old[0].body('beam').mass[0]==.8 and new[0].body('beam').mass[0]==.2
    np.testing.assert_allclose(old[0].body('beam').inertia,new[0].body('beam').inertia*4)
    assert max(x['generalized_force'] for x in old[2]['force_probes'])==.005
    assert max(x['generalized_force'] for x in new[2]['force_probes'])==.04
    a=run(motor());b=run(motor(.2,.04));assert a['samples'][-1]['qpos'][0]<.4<b['samples'][-1]['qpos'][0]
    w=motor();w['objects'][-1]['joint']['initial_position']=.3;assert run(w)['samples'][0]['qpos']==[.3]
    w2=motor();w2['objects'][-1]['dimensions_m'][0]=.8
    assert compile_world(w2)[0].body('beam').inertia[2]!=old[0].body('beam').inertia[2]


def test_general_parent_child_articulation_and_native_sensor_values():
    r=run(assembly());m=compile_world(assembly())[0]
    assert m.njnt==2 and m.body('link_two').parentid[0]==m.body('link_one').id
    assert all(abs(q)>.01 for q in r['samples'][-1]['qpos'])
    assert len(r['samples'][-1]['sensor_data'])==4 and r['independent_verification']['status']=='PASS'

@pytest.mark.parametrize('mutation',[
 lambda w:w['objects'].append(copy.deepcopy(w['objects'][0])),
 lambda w:w['objects'][0].update(parent='floor'),
 lambda w:w['objects'][0].update(position_m=[float('nan'),0,0]),
 lambda w:w['objects'][0].update(mass_kg=-1),
 lambda w:w['objects'][0].update(dimensions_m=[1e9,1,1]),
 lambda w:w.update(asset_path='/etc/passwd'),
 lambda w:w.update(revision=True),
 lambda w:w['environment'].update(duration_s=500),
 lambda w:w['objects'].extend([primitive('box','extra'+str(i)) for i in range(48)]),
])
def test_invalid_world_rejected_before_native_compilation(mutation,monkeypatch):
    w=empty_world();mutation(w)
    def forbidden(*a,**kw):raise AssertionError('Invalid world reached MuJoCo')
    monkeypatch.setattr('world.compiler.mujoco.MjModel',type('Blocked',(),{'from_xml_string':staticmethod(forbidden)}))
    with pytest.raises((ValueError,TypeError)):compile_world(w)


def test_world_safe_roundtrip_hash_and_symlink_rejection(tmp_path):
    w=assembly();store=Store(tmp_path/'worlds');key=store.save(w);assert store.get(key)==w
    assert load(json.dumps(envelope(w)).encode())==w
    v=envelope(w);v['world']['objects'][1]['position_m'][0]=.01
    with pytest.raises(ValueError):load(json.dumps(v).encode())
    with pytest.raises(ValueError):store.get('../outside')
    (tmp_path/'link').symlink_to(tmp_path/'worlds',target_is_directory=True)
    with pytest.raises(ValueError):Store(tmp_path/'link')
    (tmp_path/'worlds'/(key+'.json')).unlink();(tmp_path/'worlds'/(key+'.json')).symlink_to(tmp_path/'target')
    with pytest.raises(OSError):store.save(w)

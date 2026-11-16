"""Offline contracts/real native compilation only. No dynamics or AI evidence."""
import copy,json,threading
from types import SimpleNamespace
import mujoco,numpy as np,pytest
from ide_api import rail_sweeps as rail,rover_reference as rover,native_models as models
from ide_api.robot_import import template,validate,inspect_xml
from ide_api.toolkit import Toolkit
from ide_api import model_evidence

@pytest.fixture
def service(tmp_path):return Toolkit(tmp_path/'projects')

def test_fixed_registration_and_no_evidence_inheritance():
    d=models.descriptors();assert [x['id'] for x in d]==[models.RAIL,models.ROVER]
    assert all(x['verification']=='CURRENT_SOURCE_NATIVE_QUALIFICATION_PENDING' for x in d)
    assert models.implementation(rail.EXPERIMENT) is rail and models.implementation(rover.EXPERIMENT) is rover
    assert not d[1]['analytical'] and d[1]['policy']['primary_steps_per_case']==200
    assert 'controller_commands' in d[1]['controller']['content']

@pytest.mark.parametrize('identifier',['__import__','../rover','https://host/model','module.Class',None,{},True])
def test_no_user_code_registration(identifier):
    with pytest.raises(ValueError):models.for_model(identifier)
    with pytest.raises(ValueError):models.implementation(identifier)

@pytest.mark.parametrize('model',[models.RAIL,models.ROVER])
def test_import_export_roundtrip_save_exact_head_and_cancellation(service,model):
    d=template(model,'Offline test declaration');p=service.create(d);head=p['sha256'];assert service.export(p['id'])==d
    second=service.create(service.export(p['id']));assert second['declaration']==d and second['id']!=p['id']
    q=copy.deepcopy(d);k=next(iter(q['parameters']));q['parameters'][k]+=.01
    updated=service.save(p['id'],head,q);assert updated['revision']==1 and updated['verification']=='NOT_VERIFIED'
    with pytest.raises(ValueError,match='Stale'):service.save(p['id'],head,q)
    before=(service.root/p['id']/'head.json').read_bytes();prepared=service.prepare(q)
    assert not prepared['execution_authorized'] and prepared['native_steps']==0
    assert before==(service.root/p['id']/'head.json').read_bytes()
    assert len(service.listing())==2
    assert set(prepared['request'])=={'experiment_id','controller_id','source_sha256','cases','criteria','nonce','confirmation'}

@pytest.mark.parametrize('field,value',[('chassis_mass_kg',True),('chassis_mass_kg',1.21),('angle_deg',-1),('angle_deg',16),('friction',.6),('torque_nm',.021),('target_m',float('nan')),('wheel_radius_m',.03000001)])
def test_invalid_rover_numbers(field,value):
    d=template(models.ROVER,'Invalid negative test');d['parameters'][field]=value
    with pytest.raises(ValueError):validate(d)

@pytest.mark.parametrize('patch',[{'format':'v9'},{'controller_id':rail.CONTROLLER},{'model_id':'untrusted'}, {'source':'print(1)'},{'path':'../secret'},{'url':'https://example/model'}])
def test_unsafe_or_unsupported_declaration(patch):
    d={**template(models.ROVER,'Unsafe input'),**patch}
    with pytest.raises(ValueError):validate(d)

@pytest.mark.parametrize('payload',[b'{"format":1,"format":2}',b'{}',b'"text"',b'{' + b' '*17000 + b'}'])
def test_strict_bounded_json(payload):
    with pytest.raises(ValueError):validate(payload)

@pytest.mark.parametrize('model,key,value',[(models.RAIL,'minimumClearance',0),(models.RAIL,'maximumFinalSpeed',.1),(models.ROVER,'minimumProgress',0),(models.ROVER,'minimumUpDot',.1),(models.ROVER,'maximumTargetError',1)])
def test_mandatory_requirements_never_weaken(model,key,value):
    d=template(model,'Requirement boundary');d['requirements'][key]=value
    with pytest.raises(ValueError):validate(d)

@pytest.mark.parametrize('name,value',[('length_m',.30),('width_m',.20),('wheel_radius_m',.06),('angle_deg',15),('chassis_mass_kg',1.2)])
def test_actual_typed_model_compiles_bounds_without_integration(name,value):
    p={**rover.DEFAULTS,name:value}
    if name=='wheel_radius_m':p['length_m']=.22
    project,roles,proof,m,xml,contract=rover.compiled(p)
    assert m.nu==2 and m.njnt==5 and m.body_mass.sum()<2
    assert len(project['shape_specs'])==9 and proof['simulation']=='NOT_RUN'
    assert proof['ramp_geometry']['status']=='REAL_STATIC_NATIVE_COLLIDER'
    np.testing.assert_allclose(m.actuator_ctrlrange[:,1],p['torque_nm'])
    assert all(o['joint']['range']==[-np.pi,np.pi] for o in project['world']['objects'] if o['joint'] and o['joint']['kind']=='revolute')

@pytest.mark.parametrize('projections,expected',[([1,1],1),([-1,-1],-1),([1,-1],1)])
def test_general_controller_orientation_and_signed_commands(projections,expected):
    forward=rover.controller_commands(.04,0,.03,.012,projections);reverse=rover.controller_commands(-.04,0,.03,.012,projections)
    assert np.sign(forward[0])==expected and np.allclose(forward,-np.array(reverse))
    assert max(abs(x) for x in rover.controller_commands(10,-1,.06,.001,projections))<=.001
    assert rover.controller_commands(0,0,.03,.012,projections)==[0,0]

@pytest.mark.parametrize('args',[(.04,0,.03,.012,[1.1,1]),(True,0,.03,.012,[1,1]),(.04,0,.5,.012,[1,1]),(.04,0,.03,.2,[1,1])])
def test_controller_unsupported_axes_or_numbers(args):
    with pytest.raises(ValueError):rover.controller_commands(*args)

@pytest.mark.parametrize('model',[models.RAIL,models.ROVER])
def test_real_compile_product_design_and_prepare_leave_heads_unchanged(service,model):
    p=service.create(template(model,'Compiled declaration'));before=service.read(p['id'])
    d=service.design(p['declaration']);assert d['verification']=='COMPILED_NOT_PHYSICALLY_VERIFIED' and d['simulation']=='NOT_RUN'
    if model==models.ROVER:
        assert d['total_dynamic_mass_kg']==pytest.approx(.292)
        assert d['diagnosis']['status']=='UNVERIFIED_NO_MEASUREMENTS'
    else:assert d['initial_state']['wall_clearance']==pytest.approx(1.77)
    assert service.read(p['id'])==before and not service.results(p['id'])['results']

@pytest.mark.parametrize('xml',[ '<!DOCTYPE robot [<!ENTITY e SYSTEM "file:///etc/passwd">]><robot/>','<mujoco><include file="x.xml"/></mujoco>','<robot><link name="a"><mesh filename="https://host/mesh"/></link></robot>','<robot>'+('<x>'*15)+('</x>'*15)+'</robot>','<robot><link name="a"/><joint name="j"><parent link="missing"/><child link="a"/></joint></robot>'])
def test_xml_assets_entities_unbounded_topology_rejected(xml):
    with pytest.raises(ValueError):inspect_xml(xml)

def test_xml_structural_only_never_registers():
    urdf='<robot name="example"><link name="base"/><link name="wheel"/><joint name="hinge" type="continuous"><parent link="base"/><child link="wheel"/></joint></robot>'
    r=inspect_xml(urdf);assert r['links']==['base','wheel'] and not r['executable'] and r['registered_model'] is None
    r=inspect_xml('<mujoco><worldbody><body name="base"><geom type="box" size=".1 .1 .1"/></body></worldbody></mujoco>')
    assert r['format']=='MJCF' and r['geometry_metadata'][0]['tag']=='geom'


def request():
    return {'experiment_id':rover.EXPERIMENT,'controller_id':rover.CONTROLLER,'source_sha256':rover.source_identity(),'cases':[rover.DEFAULTS], 'criteria':rover.DEFAULT_CRITERIA,'nonce':'b'*32,'confirmation':rover.CONFIRMATION}

def test_shared_job_service_rover_cancel_restart_nonce_and_source_drift(tmp_path,monkeypatch):
    service=rail.RailSweeps(tmp_path/'jobs');r=request();calls=[]
    service.start(r,lambda fn:calls.append(fn) or {'job_id':'TEST_PROTOCOL_ONLY'});assert len(calls)==1
    assert service.start(r,lambda fn:pytest.fail('Duplicate'))['reused']
    assert rail.RailSweeps(service.root).read(r['nonce'])['status']=='INTERRUPTED'
    service.cancel(r['nonce']);service.execute(r['nonce']);assert service.read(r['nonce'])['status']=='CANCELLED'
    with pytest.raises(ValueError):service.execute(r['nonce'])
    r['nonce']='c'*32;service.start(r,lambda fn:{'job_id':'TEST_PROTOCOL_ONLY'});monkeypatch.setattr(rover,'source_identity',lambda:'f'*64)
    service.execute(r['nonce']);assert service.read(r['nonce'])['status']=='EXECUTION_ERROR'


def test_shared_service_rejects_controller_or_extra_payload_before_job(tmp_path):
    service=rail.RailSweeps(tmp_path/'jobs')
    for patch in [{'controller_id':rail.CONTROLLER},{'source':'arbitrary'},{'confirmation':rail.CONFIRMATION},{'source_sha256':'f'*64}]:
        with pytest.raises(ValueError):service.start({**request(),**patch},lambda fn:pytest.fail('No admission'))
    assert not service.root.exists()


def synthetic_forward_states():
    """TEST-ONLY repeated initial states, not a physical rollout or product evidence.

    Exercises external arithmetic/force reader integrity, never origin attestation.
    """
    p=dict(rover.DEFAULTS);c=dict(rover.DEFAULT_CRITERIA);project,roles,proof,m,xml,contract=rover.compiled(p);world=project['world']
    d=__import__('world.compiler',fromlist=['initial_state']).initial_state(m,world);mujoco.mj_forward(m,d);origin=d.xpos[m.body(roles['root_body_id']).id].copy();tangent,normal=rover.frame(p);samples=[]
    for i in range(201):
        d.time=i*.005;rover.reference_controller(m,d,p,roles,origin,tangent,normal);mujoco.mj_forward(m,d);samples.append(rover.snapshot(m,d,p,{**roles,'world':world},origin,tangent))
    metrics,checks=rover.measure(samples,p,c,m,roles);checks['fresh_replay']=True
    value={'execution_status':'MEASURED','verdict':'FAIL','metrics':metrics,'checks':checks,'failure_reasons':[k for k,v in checks.items() if not v],'comparison':{'meaning':'SYNTHETIC_TEST_ONLY_NOT_NATIVE'},'samples':samples,'trajectory_sha256':rail.digest(samples),'model_xml':xml,'effective_model_sha256':__import__('hashlib').sha256(xml.encode()).hexdigest(),'world':world,'roles':roles,'compiled_contract':contract,'construction_proof':proof,'independent_readback':rover.forward_audit(samples,p,roles,m,world),'replay':{'status':'PASS','primary_steps':200,'fresh_steps':200,'samples':copy.deepcopy(samples),'trajectory_sha256':rail.digest(samples)},'controller_contract':{'id':rover.CONTROLLER,'runtime_controls':'Registered target PD feedback; compiler constant command is only the initial authoring/probe value','kp_n_per_m':3.,'kd_ns_per_m':.8},'engine_version':mujoco.__version__,'units':rover.UNITS,'limitations':rover.LIMITATIONS,'model_id':models.ROVER,'measurement_definition':'ROVER_TARGET_SAMPLED_V1','experiment_id':rover.EXPERIMENT,'controller_id':rover.CONTROLLER,'source_sha256':rover.source_identity(),'parameters':p,'criteria':c,'simulation_configuration':{'duration_s':1.,'timestep_s':.005,'initial_position_m':0.}}
    value['case_id']=rail.digest({'source':value['source_sha256'],'experiment':rover.EXPERIMENT,'controller':rover.CONTROLLER,'parameters':p,'criteria':c})
    return value

@pytest.fixture(scope='module')
def synthetic():return synthetic_forward_states()

def test_external_reader_positive_is_integrity_not_native_attestation(synthetic):
    checked=model_evidence.verify_package(model_evidence.package(synthetic));assert checked['status']=='INTEGRITY_VALID_EXTERNAL_UNVERIFIED' and checked['new_native_steps']==0
    assert checked['record']['verdict']=='FAIL'
    assert model_evidence.diagnose(synthetic)['status']=='MEASURED_REQUIREMENT_FAILURE'

@pytest.mark.parametrize('target',['source','model','criteria','replay','samples','force','verdict','hash','extra'])
def test_external_evidence_corrupt_or_incompatible_rejected(synthetic,target):
    r=copy.deepcopy(synthetic)
    if target=='source':r['source_sha256']='f'*64
    elif target=='model':r['model_id']=models.RAIL
    elif target=='criteria':r['criteria']['minimumProgress']=0
    elif target=='replay':r['replay']['fresh_steps']=0
    elif target=='samples':r['samples'].pop()
    elif target=='force':r['samples'][0]['actuator_force'][0]=100
    elif target=='verdict':r['verdict']='PASS'
    elif target=='extra':r['path']='arbitrary'
    else:r['trajectory_sha256']='0'*64
    with pytest.raises((ValueError,AssertionError)):model_evidence.verify_package({'format':model_evidence.FORMAT,'sha256':rail.digest(r),'result':r})


def test_wrong_project_result_and_cross_model_comparison_rejected(service,synthetic):
    p=service.create(template(models.ROVER,'No evidence'))
    with pytest.raises(ValueError):service.result(p['id'],'b'*32,synthetic['case_id'])
    with pytest.raises(ValueError):model_evidence.compare(synthetic,synthetic)
    bad=copy.deepcopy(synthetic);bad['model_id']=models.RAIL
    with pytest.raises(ValueError):model_evidence.compare(synthetic,bad)

@pytest.fixture
def server(service):
    from ide_api.server import Server
    server=Server(('127.0.0.1',0),ide=SimpleNamespace(_toolkit=service));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    yield server
    server.shutdown();server.server_close();t.join()

def http(server,path,body=None,origin=True,token=True):
    from http.client import HTTPConnection
    c=HTTPConnection(server.host,timeout=10);headers={'Host':server.host}
    if origin:headers['Origin']='http://'+server.host
    if token:headers['X-EMBODY-Token']=server.token
    if body is not None:headers['Content-Type']='application/json'
    c.request('POST' if body is not None else 'GET','/api/toolkit/'+path,None if body is None else json.dumps(body),headers);r=c.getresponse();value=json.loads(r.read());c.close();return r.status,value

def test_actual_guarded_toolkit_http(server):
    assert http(server,'catalog')[0]==200
    code,p=http(server,'new',{'title':'HTTP rover','model_id':models.ROVER});assert code==200
    assert http(server,'export?id='+p['id'])[1]==p['declaration']
    assert http(server,'prepare',{'declaration':p['declaration']})[1]['execution_authorized'] is False
    assert http(server,'new',{'title':'blocked','model_id':models.ROVER},origin=False)[0]==403
    assert http(server,'new',{'title':'blocked','model_id':models.ROVER},token=False)[0]==403
    assert http(server,'project?id=../secret')[0]==400
    assert http(server,'new',{'title':'extra','model_id':models.ROVER,'source':'x'})[0]==400
    for name in ['execute','start','approve','apply','provider']:
        assert http(server,name,{})[0]==403

def test_string_import_keeps_duplicate_key_rejection_and_roundtrip(service):
    d=template(models.ROVER,'String import');raw=json.dumps(d);assert service.create(raw)['declaration']==d
    duplicate=raw.replace('"format":', '"format":"invalid", "format":',1)
    with pytest.raises(ValueError,match='Duplicate'):service.create(duplicate)


def test_native_axes_commands_force_probes_without_motion():
    p=rover.DEFAULTS;project,roles,proof,m,xml,compiled=rover.compiled(p)
    from world.compiler import initial_state
    d=initial_state(m,project['world']);mujoco.mj_forward(m,d);origin=d.xpos[m.body(roles['root_body_id']).id].copy();tangent,normal=rover.frame(p)
    rover.reference_controller(m,d,p,roles,origin,tangent,normal);mujoco.mj_forward(m,d)
    assert all(x<0 for x in d.ctrl) # actual axes in this generated model; not a general sign rule
    assert max(abs(x) for x in d.ctrl)<=p['torque_nm']
    for i in range(m.nu):
        dof=m.jnt_dofadr[m.actuator_trnid[i,0]];assert d.qfrc_actuator[dof]==pytest.approx(d.actuator_force[i])


def test_qualification_scopes_exact_budgets_no_authority():
    from tools.model_qualification import prepare,check
    total=0
    for model,steps in [(models.RAIL,2400),(models.ROVER,800)]:
        manifest=prepare(model);assert manifest['authorization']=='NOT_GRANTED'
        result=check(manifest);assert result['status']=='IDENTITIES_VALID_NO_EXECUTION_AUTHORITY'
        assert result['limits']['native_rollouts']==4 and result['limits']['maximum_integration_steps']==steps
        assert result['execution_authorized'] is False and result['new_native_steps']==0
        total+=steps
    assert total==3200

@pytest.mark.parametrize('field',['source','base','expiry','nonce','limits','request'])
def test_qualification_drift_and_consumption_fail_closed(tmp_path,monkeypatch,field):
    from tools import model_qualification as q
    manifest=q.prepare(models.ROVER);d=manifest['definition']
    if field=='source':d['source_manifest']['ide_api/rover_reference.py']='0'*64
    elif field=='base':d['base_commit']='0'*40
    elif field=='expiry':d['expires_utc']='2000-01-01T00:00:00+00:00'
    elif field=='limits':d['limits']['maximum_integration_steps']+=1
    elif field=='request':d['request']['cases'][0]['angle_deg']=1
    else:
        monkeypatch.setattr(q,'ROOT',tmp_path)
        # Preserve source/base checks to exercise the nonce gate independently.
        monkeypatch.setattr(q,'sources',lambda:d['source_manifest'])
        p=tmp_path/'.runtime/rail_sweeps'/d['request']['nonce'];p.mkdir(parents=True)
    manifest['sha256']=rail.digest(d)
    with pytest.raises(ValueError):q.check(manifest)


def test_rehashed_force_tampering_cannot_pass_independent_native_readback(synthetic):
    value=copy.deepcopy(synthetic)
    for seq in [value['samples'],value['replay']['samples']]:seq[0]['actuator_force'][0]+=.001
    value['trajectory_sha256']=rail.digest(value['samples']);value['replay']['trajectory_sha256']=rail.digest(value['replay']['samples'])
    # Recompute claimed metrics as well; actual native forwarding must still refuse it.
    p,roles,proof,m,xml,contract=rover.compiled(value['parameters']);metrics,checks=rover.measure(value['samples'],value['parameters'],value['criteria'],m,roles);checks['fresh_replay']=True;value['metrics']=metrics;value['checks']=checks
    with pytest.raises((ValueError,AssertionError)):model_evidence.verify_result(value)


def test_coupled_wheelbase_clearance_rejects_overlapping_wheels():
    with pytest.raises(ValueError,match='2 mm'):rover.parameters({**rover.DEFAULTS,'wheel_radius_m':.06})
    assert rover.parameters({**rover.DEFAULTS,'wheel_radius_m':.06,'length_m':.22})['wheel_radius_m']==.06


def test_rehashed_incomplete_state_vector_rejected(synthetic):
    v=copy.deepcopy(synthetic)
    for samples in [v['samples'],v['replay']['samples']]:samples[0]['qvel']=[0.]
    v['trajectory_sha256']=rail.digest(v['samples']);v['replay']['trajectory_sha256']=rail.digest(v['replay']['samples'])
    with pytest.raises(ValueError,match='Incomplete'):model_evidence.verify_result(v)


def test_partial_or_zero_axis_projection_scales_control_without_inventing_direction():
    full=rover.controller_commands(.04,0,.03,.012,[1,-1])
    half=rover.controller_commands(.04,0,.03,.012,[.5,0])
    assert half[0]==pytest.approx(full[0]/2) and half[1]==0

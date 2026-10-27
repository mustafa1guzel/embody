"""Independent references and actual trusted MuJoCo dynamics. No live VM here."""
from dataclasses import replace
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import mujoco
import numpy as np
import pytest
from core.simulation import ROOT
from core.robots.arm import ArmFamily,TARGET,MODEL
from core.robots.registry import get_family
from core.robots.execution import first_run,independent,acceptance
from core.robots.reference import reference_controller
from core.agent.tools import AgentTools
from core.agent.patching import CandidateStore,read_project_file
from core.agent.trace import ExecutionTrace
from core.agent.vm_backend import AppleVMBackend
from core.agent.vm_protocol import command_reply,ProtocolError
from physics.multidof import MultiDOFContract,JointLimit
from physics.planar import forward,jacobian,inverse,assess
from physics.vector_profiler import profile
from workspace.workflow import Workflow,WorkflowBlocked


@pytest.fixture(scope='module')
def family():return ArmFamily(evaluation=True)


def test_hand_kinematics_and_jacobian():
    assert forward((2,1),(0,0))==pytest.approx((3,0))
    assert forward((2,1),(math.pi/2,0))==pytest.approx((0,3),abs=1e-14)
    assert forward((2,1),(0,math.pi/2))==pytest.approx((2,1))
    np.testing.assert_allclose(jacobian((2,1),(0,0)),[[0,0],[3,1]],atol=1e-14)
    np.testing.assert_allclose(jacobian((2,1),(0,math.pi/2)),[[-1,-1],[2,0]],atol=1e-14)


def test_generated_fk_ik_jacobian_against_mujoco(family):
    m,_,c,_,_,lengths=family.compile('arm_nominal');d=mujoco.MjData(m);rng=random.Random(903)
    for _ in range(100):
        q=[rng.uniform(*j.position_range) for j in c.joints];d.qpos[:]=q;mujoco.mj_forward(m,d)
        np.testing.assert_allclose(forward(lengths,q),d.site_xpos[m.site('end_effector').id,:2],atol=1e-12)
        jp=np.zeros((3,2));jr=np.zeros((3,2));mujoco.mj_jacSite(m,d,jp,jr,m.site('end_effector').id)
        np.testing.assert_allclose(jacobian(lengths,q),jp[:2],atol=1e-12)
        target=forward(lengths,q);solutions=inverse(lengths,target,[j.position_range for j in c.joints])
        assert solutions
        for witness in solutions:np.testing.assert_allclose(forward(lengths,witness),target,atol=1e-10)
        eps=1e-6
        finite_diff=np.column_stack([(np.array(forward(lengths,[v+(eps if i==j else 0) for i,v in enumerate(q)]))-
                                     np.array(forward(lengths,[v-(eps if i==j else 0) for i,v in enumerate(q)])))/(2*eps) for j in range(2)])
        np.testing.assert_allclose(jacobian(lengths,q),finite_diff,atol=1e-9)


def test_reach_joint_limits_singularities_and_tolerance_ball(family):
    _,_,c,_,_,L=family.compile('arm_nominal')
    assert assess(c,L)['kinematic_feasibility']=='FEASIBLE'
    assert assess(c,L)['dynamic_feasibility']=='UNKNOWN'
    _,_,u,_,_,_=family.compile('arm_unreachable')
    result=assess(u,L);assert result['status']=='PROVEN_INFEASIBLE'
    assert result['distance_to_unrestricted_workspace_m']==pytest.approx(.95)
    singular=replace(c,target_m=(sum(L),0,.25))
    assert any(assess(singular,L)['singular_witnesses'])
    near=replace(c,target_m=(sum(L)+.01,0,.25))
    assert assess(near,L)['status']=='UNKNOWN' # Exact center outside is not whole tolerance-ball infeasible.
    restricted=replace(c,joints=tuple(replace(j,position_range=(-.1,.1)) for j in c.joints),q0=(0,0))
    assert assess(restricted,L)['status']=='UNKNOWN'
    assert assess(c,L,premises=False)['status']=='UNKNOWN'
    assert assess(replace(c,target_m=(.6,.2,1)),L)['status']=='PROVEN_INFEASIBLE'
    assert inverse((2,1),(0,0),[(-math.pi,math.pi)]*2)==[]


@pytest.mark.parametrize('target', [(float('nan'),0),(float('inf'),0),('bad',0),(0,)])
def test_invalid_kinematic_targets(target):
    with pytest.raises((ValueError,TypeError)):inverse((1,1),target,[(-1,1)]*2)


@pytest.mark.parametrize('field,value', [('q0',(0,)),('v0',(0,0,0)),('q0',(9,0)),
    ('duration_s',0),('timestep_s',0),('target_m',(0,float('nan'),0)),('target_tolerance_m',-1),
    ('final_velocity_limit',6),('settling_window_s',5),('no_contact','yes'),('model_sha256','bad'),
    ('joint_axes_world',((0,0,2),(0,0,1))),('frame','unknown')])
def test_multidof_contract_validation(family,field,value):
    c=family.compile('arm_nominal')[2]
    with pytest.raises(ValueError):replace(c,**{field:value})


def test_contract_identity_serialization_and_dimensions(family):
    c=family.compile('arm_nominal')[2]
    assert MultiDOFContract.from_dict(c.to_dict())==c
    assert MultiDOFContract.from_dict(c.to_dict()).identity==c.identity
    assert c.identity!=family.compile('arm_alternate')[2].identity
    with pytest.raises(ValueError):JointLimit('bad','revolute','m','N',(-1,1),(-2,2))
    assert c.joints[0].effort_range==(-3,3) and c.joints[1].effort_range==(-1.5,1.5)


def test_effective_mass_force_and_gravity_are_real_compiled_parameters(family):
    m,_,c,b,_,_=family.compile('arm_nominal');d=mujoco.MjData(m)
    for q in ((0,0),(.4,-.9),(2.5,-2.3)):
        d.qpos[:]=q;d.qvel[:]=0;d.ctrl[:]=[-1000,1000];mujoco.mj_forward(m,d)
        np.testing.assert_allclose(d.qfrc_bias,[0,0],atol=1e-12)
        np.testing.assert_allclose(d.actuator_force,[-3,1.5],atol=1e-12)
        np.testing.assert_allclose(d.qfrc_actuator,[-3,1.5],atol=1e-12)
        M=np.empty((2,2));mujoco.mj_fullM(m,d,M);assert np.linalg.eigvalsh(M).min()>0
        assert abs(M[0,1])>.001
    assert b['body_masses_kg']['link1']==1 and b['body_masses_kg']['link2']==.6


def test_real_baseline_failure_and_reference_achievability(family):
    c=family.compile('arm_nominal')[2]
    failed=first_run(family,'arm_nominal',family.baseline(),c.controller_sha256)
    actual=acceptance(failed['samples'],c)
    assert actual['status']=='FAIL' and actual['checks']['torque_limits']
    assert not actual['checks']['maximum_velocity'] and not actual['checks']['joint_limits']
    assert independent(failed,None,None,family=family)['verification_execution']=='PASS'
    source_hash=hashlib.sha256((ROOT/'core/robots/reference.py').read_bytes()).hexdigest()
    benchmark=first_run(family,'arm_nominal',reference_controller,source_hash)
    assert acceptance(benchmark['samples'],benchmark['contract'])['status']=='PASS'
    p=profile(benchmark['samples'],benchmark['contract']);assert p['status']=='AVAILABLE'
    assert len(p['signed_actuator_work_j'])==2 and p['electrical_energy']=='NOT_AVAILABLE'
    assert max(p['saturation_fraction'])<=1
    broken=copy.deepcopy(benchmark['samples']);broken[2]['qvel_rad_s'].pop()
    assert profile(broken,benchmark['contract'])['status']=='NOT_AVAILABLE'


def test_same_six_tools_scoped_family_routes_and_unreachable_rejection(tmp_path):
    t=AgentTools(tmp_path/'tools',ExecutionTrace(tmp_path/'trace',model_mode='offline_test'),family='arm')
    assert len(t.schemas)==6
    enums={s['name']:s for s in t.schemas}
    assert enums['propose_patch']['parameters']['properties']['target_path']['enum']==[TARGET]
    assert 'configs/arm_evaluation.json' not in enums['read_project']['parameters']['properties']['path']['enum']
    assert t.dispatch('read_project',{'path':'robot/controller.py'})['ok'] is False
    assert t.dispatch('read_project',{'path':TARGET})['ok']
    ctx=t.dispatch('get_robot_context',{'scenario_id':'arm_nominal'})['result']
    assert ctx['bodybase']['joint_count']==2
    result=t.dispatch('run_simulation',{'scenario_id':'arm_unreachable','controller_variant':'faulty'})['result']
    assert result['simulation_execution']=='NOT_RUN' and result['task_rejection_verified']
    real=t.dispatch('run_simulation',{'scenario_id':'arm_nominal','controller_variant':'faulty'})['result']
    d=t.dispatch('inspect_failure',{'simulation_run_id':real['simulation_run_id']})['result']
    assert d['evidence']['measured_acceptance']['status']=='FAIL'
    with pytest.raises(ValueError):get_family('arbitrary.module')


@pytest.mark.parametrize('attack', ['import os\n','\nopen("secret")\n','\n# source change\n'])
def test_family_source_policy_never_relaxes_permissions(tmp_path,attack):
    store=CandidateStore(ROOT,tmp_path,target=TARGET);original=read_project_file(ROOT,TARGET,{TARGET})
    p=store.propose(target_path=TARGET,expected_original_sha256=original['sha256'],
        proposed_source=original['content']+attack,explanation='Developer source-policy test')
    assert p['validation_status']==('VALID' if attack.startswith('\n#') else 'REJECTED')
    with pytest.raises(ValueError):store.propose(target_path='robot/controller.py',expected_original_sha256=original['sha256'],proposed_source='x',explanation='blocked')


def test_arm_review_approval_and_install_scope_fail_closed(tmp_path,monkeypatch):
    root=tmp_path/'project';root.mkdir()
    for name in ('core','physics','robot','configs','workspace'):
        shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__','approved_controller.py','approved_arm_controller.py'))
    w=Workflow(root,tmp_path/'review',family='arm');original=read_project_file(root,TARGET,{TARGET})
    r=w.create(source=original['content']+'\n# developer review test\n',explanation='No execution',expected_original_sha256=original['sha256'],provenance={'kind':'developer_test'})
    assert w.get(r)['apply_target']=='robot/approved_arm_controller.py'
    with pytest.raises(WorkflowBlocked):w.verify(r,approved=False)
    with pytest.raises(WorkflowBlocked):w.apply(r,confirmation='APPLY '+w.get(r)['source_sha256'])
    with pytest.raises(WorkflowBlocked):Workflow(root,w.sessions).get(r)
    dev=Workflow(root,tmp_path/'dev',family='arm',evaluation=False)
    with pytest.raises(WorkflowBlocked,match='Development-only'):dev.apply('bad',confirmation='x')
    assert not (root/'robot/approved_arm_controller.py').exists()


def test_two_actuator_wire_still_rejects_verdicts_and_invalid_vectors():
    assert command_reply({'v':1,'seq':0,'ctrl':[1,-1]},0,2)==[1,-1]
    for reply in ({'v':1,'seq':0,'ctrl':[1]}, {'v':1,'seq':0,'ctrl':[1,2],'safe':True}):
        with pytest.raises(ProtocolError):command_reply(reply,0,2)


def test_candidate_cannot_run_without_qualified_backend(tmp_path):
    from core.agent.verification import CandidateVerifier
    f=ArmFamily();store=CandidateStore(ROOT,tmp_path/'store',target=TARGET);o=read_project_file(ROOT,TARGET,{TARGET})
    p=store.propose(target_path=TARGET,expected_original_sha256=o['sha256'],proposed_source=o['content']+'\n# not a repair\n',explanation='No execution')
    v=CandidateVerifier(store,f.scenarios,tmp_path/'verification',ExecutionTrace(tmp_path/'trace',model_mode='offline'),family=f)
    result=v.verify(p['candidate_id']);assert result['verification_execution']=='BLOCKED'
    assert result['candidate_code_executed'] is False


def test_additional_two_dof_qualification_is_identity_and_model_bound(tmp_path,monkeypatch,family):
    from types import SimpleNamespace
    from core.robots import qualification as q
    from core.agent.vm_backend import IsolationBlocked
    backend=SimpleNamespace(config={'certificate':str(tmp_path/'containment.json')})
    with pytest.raises(IsolationBlocked,match='missing'):q.require_qualification(backend,family)
    identity={'unit_test':'mock identity, not actual containment'};monkeypatch.setattr(q,'identity',lambda _:identity)
    proof={'status':'PASS','identity':identity,'created_unix':q.time.time(),
           'probe_sha256':hashlib.sha256(q.PROBE_SOURCE.encode()).hexdigest(),
           'model_hashes':{s:family.compile(s)[2].model_sha256 for s in family.scenarios}}
    path=tmp_path/'arm_qualification.json';path.write_text(json.dumps(proof))
    assert q.require_qualification(backend,family)==proof
    for key,value in [('status','FAIL'),('identity',{}),('created_unix',0),('model_hashes',{}),('probe_sha256','x')]:
        invalid={**proof,key:value};path.write_text(json.dumps(invalid))
        with pytest.raises(IsolationBlocked):q.require_qualification(backend,family)


def pinned_protected_project(tmp_path,monkeypatch):
    """Use the real pinned loader and exact inventories, never substitute it."""
    from core import day4b1
    project=tmp_path/'project';project.mkdir()
    baseline=ROOT/'artifacts/day4b1/implementation/before.json'
    original=json.loads(baseline.read_text())
    for relative in original:
        source=ROOT/relative;target=project/relative
        if source.is_file():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    selected=Path('artifacts/phase18e_2/20261025/security/protected_baseline_v2.json')
    (project/selected).parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/selected,project/selected)
    output=tmp_path/'gate';output.mkdir()
    shutil.copyfile(baseline,output/'before.json')
    monkeypatch.setattr(day4b1,'ROOT',project);monkeypatch.setattr(day4b1,'OUTPUT',output)
    # At least one originally inventoried Finder path exercises the actual
    # exception rather than an untracked extra file.
    finder=project/next(name for name in original if Path(name).name=='.DS_Store')
    finder.parent.mkdir(parents=True,exist_ok=True)
    return project,output,finder

def test_qualification_ignores_only_finder_metadata_not_physics(tmp_path,monkeypatch):
    from core import day4b1
    project,_,finder=pinned_protected_project(tmp_path,monkeypatch)
    assert day4b1.reviewed_protected_inventory()==json.loads((ROOT/'artifacts/phase18e_2/20261025/security/protected_baseline_v2.json').read_text())['files']
    assert day4b1.original_project_intact()
    finder.write_text('Finder metadata changed')
    assert day4b1.original_project_intact()
    model=project/'robot/rail_carriage.xml'
    model.write_text('physics changed')
    assert not day4b1.original_project_intact()

@pytest.mark.parametrize('which',['predecessor','version2'])
def test_pinned_loader_rejects_arbitrary_baseline_substitution(tmp_path,monkeypatch,which):
    from core import day4b1
    from core.agent.vm_backend import IsolationBlocked
    project,output,_=pinned_protected_project(tmp_path,monkeypatch)
    target=output/'before.json' if which=='predecessor' else project/'artifacts/phase18e_2/20261025/security/protected_baseline_v2.json'
    target.write_text(json.dumps({'robot/rail_carriage.xml':'0'*64}))
    with pytest.raises(IsolationBlocked,match='Versioned protected baseline identity differs'):
        day4b1.original_project_intact()

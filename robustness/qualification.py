"""Additional source/matrix-bound model qualification; never substitutes base containment."""
import hashlib
from pathlib import Path
import time
import mujoco
import numpy as np
from core.agent.vm_backend import AppleVMBackend,IsolationBlocked,identity
from .contracts import write_once
from .perturbation import compile_scenario

PROBE='''def faulty_braking_controller(model,data):
    data.ctrl[0]=0.17*data.qpos[0]+0.13*data.qvel[0]+0.07*data.time+0.03*data.qfrc_applied[0]
    if model.nu==2:
        data.ctrl[1]=0.11*data.qpos[1]-0.19*data.qvel[0]+0.05*data.time+0.02*data.qfrc_applied[1]
'''


def check_approval(experiment,approved_sha):
    if approved_sha!=experiment.identity:raise IsolationBlocked('Fresh explicit approval for this exact Day 10 batch is required')
    experiment.assert_current()


def qualify(experiment,backend,folder,*,approved_sha):
    check_approval(experiment,approved_sha)
    if type(backend) is not AppleVMBackend:raise IsolationBlocked('Only AppleVMBackend is supported')
    base=backend.preflight();rows=[]
    for family in ('rail','arm'):
        cases=[r for r in experiment.data['matrix'] if r['family']==family]
        for row in (cases[0],next(r for r in reversed(cases) if r['stratum']=='boundary')):
            plant=compile_scenario(row,experiment.data['sources'][family]['repair']['sha256']);model=plant['model'];data=mujoco.MjData(model)
            c=plant['contract']
            with backend.controller(PROBE,plant['xml']) as (remote,exchanges,ready):
                for k in range(3):
                    data.qpos[:]=([c.initial_position_m+.01*k] if family=='rail' else np.array(c.q0)*(.99**k))
                    data.qvel[:]=[.11,-.17][:model.nv];data.qfrc_applied[:]=[.07,.09][:model.nv];data.time=.23*k
                    data.qacc_warmstart[:]=[.01,-.02][:model.nv];mujoco.mj_forward(model,data)
                    expected=[.17*data.qpos[0]+.13*data.qvel[0]+.07*data.time+.03*.07]
                    if model.nu==2:expected.append(.11*data.qpos[1]-.19*data.qvel[0]+.05*data.time+.02*.09)
                    remote(model,data);delta=float(np.max(np.abs(data.ctrl-expected)))
                    rows.append({'scenario_id':row['id'],'sample':k,'maximum_command_difference':delta,'state_size':ready['state_size'],'model_sha256':ready['xml_sha256']})
    proof={'status':'PASS' if all(r['maximum_command_difference']<=1e-12 for r in rows) else 'FAIL',
        'experiment_sha256':experiment.identity,'identity':identity(backend.config),'created_unix':time.time(),
        'base_containment_created_unix':base['created_unix'],'rows':rows,'probe_sha256':hashlib.sha256(PROBE.encode()).hexdigest(),
        'scope':'Four representative compiled models / twelve state-action probes, not a dynamic safety verdict for all models.',
        'matrix_model_hashes':{r['id']:r['model_sha256'] for r in experiment.data['matrix']}}
    write_once(Path(folder)/'qualification.json',proof);(Path(folder)/'probe_source.txt').write_text(PROBE)
    return proof


def require(experiment,backend,proof,approved_sha):
    check_approval(experiment,approved_sha)
    if type(backend) is not AppleVMBackend:raise IsolationBlocked('Only the qualified AppleVMBackend may run frozen candidates')
    base=backend.preflight()
    if (proof.get('status')!='PASS' or proof.get('experiment_sha256')!=experiment.identity
            or proof.get('identity')!=identity(backend.config) or proof.get('base_containment_created_unix')!=base['created_unix']
            or not 0<=time.time()-proof.get('created_unix',0)<=86400
            or proof.get('probe_sha256')!=hashlib.sha256(PROBE.encode()).hexdigest()
            or proof.get('matrix_model_hashes')!={r['id']:r['model_sha256'] for r in experiment.data['matrix']}):
        raise IsolationBlocked('Benchmark model/source qualification is missing, stale or mismatched')
    return proof

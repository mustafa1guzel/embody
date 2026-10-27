"""Operator-only two-DOF communication qualification, after existing containment."""
import hashlib
import json
from pathlib import Path
import time
import mujoco
import numpy as np
from core.agent.vm_backend import AppleVMBackend,IsolationBlocked,identity
from core.simulation import write_json
from core.robots.arm import ArmFamily

# A transparent developer probe, not a repair or model-generated controller.
PROBE_SOURCE = '''def faulty_braking_controller(model, data):
    data.ctrl[0] = 0.2*data.qpos[0] + 0.3*data.qvel[1] + 0.01*data.time + 0.05*data.qfrc_applied[0]
    data.ctrl[1] = 0.4*data.qpos[1] - 0.1*data.qvel[0] + 0.02*data.time + 0.03*data.qfrc_applied[1]
'''


def require_qualification(backend,family):
    path=Path(backend.config['certificate']).with_name('arm_qualification.json')
    try:proof=json.loads(path.read_text())
    except (OSError,ValueError) as exc:raise IsolationBlocked('Two-DOF qualification is missing') from exc
    if proof.get('status')!='PASS' or proof.get('identity')!=identity(backend.config):
        raise IsolationBlocked('Two-DOF qualification is stale or failed')
    if not 0<=time.time()-proof.get('created_unix',0)<=86400:
        raise IsolationBlocked('Two-DOF qualification expired')
    if proof.get('probe_sha256')!=hashlib.sha256(PROBE_SOURCE.encode()).hexdigest():
        raise IsolationBlocked('Two-DOF qualification probe changed')
    for scenario in family.scenarios:
        if proof.get('model_hashes',{}).get(scenario)!=family.compile(scenario)[2].model_sha256:
            raise IsolationBlocked('Two-DOF qualified model differs')
    return proof


def qualify(backend,output):
    """Developer probes only. No untrusted code and no image pull."""
    backend.preflight();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    family=ArmFamily(evaluation=True);rows=[];models={}
    for scenario in family.scenarios:
        model,xml,c,_,_,_=family.compile(scenario);models[scenario]=c.model_sha256
        data=mujoco.MjData(model)
        with backend.controller(PROBE_SOURCE,xml) as (remote,exchanges,ready):
            for k,(q,v) in enumerate([((0,.3),(.1,-.2)),((1,-1.2),(-.3,.4)),((2.55,-2.3),(.2,.1))]):
                data.qpos[:]=q;data.qvel[:]=v;data.time=.23*k;data.qfrc_applied[:]=[.17,-.13]
                data.qacc_warmstart[:]=[.02,-.04];data.ctrl[:]=[.12,-.17];mujoco.mj_forward(model,data)
                expected=[.2*q[0]+.3*v[1]+.01*data.time+.05*.17,
                          .4*q[1]-.1*v[0]+.02*data.time+.03*(-.13)]
                remote(model,data);difference=float(np.max(np.abs(data.ctrl-expected)))
                rows.append({'scenario':scenario,'sample':k,'qpos_rad':list(q),'qvel_rad_s':list(v),
                             'expected':expected,'actual':data.ctrl.tolist(),'maximum_difference':difference,
                             'state_size':ready['state_size'],'model_sha256':ready['xml_sha256']})
    proof={'status':'PASS' if rows and all(r['maximum_difference']<=1e-12 for r in rows) else 'FAIL',
           'identity':identity(backend.config),'created_unix':time.time(),'model_hashes':models,
           'probe_sha256':hashlib.sha256(PROBE_SOURCE.encode()).hexdigest(),'rows':rows,
           'scope':'Developer-authored nonsymmetric two-joint state/action parity after existing containment qualification. Not candidate safety.'}
    write_json(output/'arm_qualification.json',proof);(output/'probe_source.txt').write_text(PROBE_SOURCE)
    if proof['status']=='PASS':write_json(Path(backend.config['certificate']).with_name('arm_qualification.json'),proof)
    return proof

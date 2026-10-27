"""Evidence and scene read models; no candidate imports and no host evaluation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import mujoco
import numpy as np
from core.agent.patching import READ_ALLOWLIST, read_project_file
from core.simulation import ROOT
from workspace.data import default_recording, physical_context, EvidenceError
from workspace.workflow import Workflow

VARIANTS = ('original', 'attempt_1', 'attempt_2')
ARTIFACTS = {'recording/diagnosis.txt':'model_diagnosis.txt',
             'recording/final_report.md':'final_report.md',
             'recording/agent_trace.jsonl':'session/execution_trace.jsonl'}


class IDE:
    def __init__(self, *, workflow=None, recording=None):
        self.workflow = workflow or Workflow(sessions=ROOT/'artifacts/day7/workflows')
        self.recording = recording or default_recording()
        self.arm_workflow = Workflow(sessions=ROOT/'artifacts/day9/workflows',family='arm')

    @property
    def studio_execution(self):
        from ide_api.studio_execution import StudioExecution
        if not hasattr(self,'_studio_execution'):self._studio_execution=StudioExecution(self.engineering_ai)
        return self._studio_execution

    @property
    def ramp(self):
        from ide_api.ramp import RampService
        if not hasattr(self,'_ramp'):self._ramp=RampService()
        return self._ramp

    @property
    def engineering_ai(self):
        from ide_api.engineering_ai import EngineeringAI
        if not hasattr(self,'_engineering_ai'):
            self._engineering_ai=EngineeringAI(ROOT/'artifacts/phase19c/workspace_requests')
        return self._engineering_ai

    @property
    def engineering(self):
        from ide_api.engineering import EngineeringService
        active=self.creation.active()
        if active is not None:return active
        if not hasattr(self,'_engineering'):self._engineering=EngineeringService()
        return self._engineering

    @property
    def creation(self):
        from engineering.creation import CreationManager
        if not hasattr(self,'_creation'):self._creation=CreationManager()
        return self._creation

    @property
    def construction_review(self):
        from engineering.verified_construction import VerifiedConstruction
        if not hasattr(self,'_construction_review'):self._construction_review=VerifiedConstruction()
        return self._construction_review

    @property
    def hardware(self):
        from ide_api.hardware import HardwareService
        if not hasattr(self,'_hardware'):self._hardware=HardwareService()
        return self._hardware

    def robustness(self):
        from robustness.reporting import offline_report
        return offline_report(ROOT/'artifacts/day10_12/20261024_combined/release_v3/robustness')

    def arm_recording(self):
        from workspace.arm_data import default_arm_recording
        return default_arm_recording()

    def arm_file(self,path):
        from core.robots.arm import READS
        return {**read_project_file(ROOT,path,READS),'historical':False}

    def files(self):
        return [{'path':p, 'historical':False} for p in sorted(READ_ALLOWLIST)] + [
            {'path':p, 'historical':True} for p, recorded in ARTIFACTS.items()
            if recorded in self.recording.inventory] + [
            {'path':f'recording/{v}/controller.py', 'historical':True} for v in VARIANTS[1:]]

    def physics(self, scenario, variant):
        # Read-only deterministic arithmetic over pinned evidence. No model/VM/action.
        from physics.reports import recorded_report
        return recorded_report(scenario, variant, recording=self.recording)

    def file(self, path):
        if path in READ_ALLOWLIST:
            return {**read_project_file(ROOT,path),'historical':False}
        if path in ARTIFACTS:
            raw = self.recording.read(ARTIFACTS[path])
        elif path in [f'recording/{v}/controller.py' for v in VARIANTS[1:]]:
            raw = self.recording.proposal(path.split('/')[1])['source'].encode()
        else:
            raise EvidenceError('File is not authorized')
        return {'path':path,'content':raw.decode(),'sha256':hashlib.sha256(raw).hexdigest(),'historical':True}

    def experiment(self, scenario):
        trajectories = {v:self.recording.trajectory(scenario,v) for v in VARIANTS}
        context = physical_context(scenario,trajectories['original'])
        if any(t['xml']!=trajectories['original']['xml'] or [s['time'] for s in t['samples']]!=[s['time'] for s in trajectories['original']['samples']] for t in trajectories.values()):
            raise EvidenceError('Comparison requires identical compiled geometry and measured timestamp grids')
        # Scene transforms come from MuJoCo, not a parallel hand-written robot.
        model = mujoco.MjModel.from_xml_string(trajectories['original']['xml'])
        data = mujoco.MjData(model)
        first = trajectories['original']['samples'][0]
        data.qpos[0],data.qvel[0] = first['position'],first['velocity']
        mujoco.mj_forward(model,data)
        if model.nq != 1 or model.nv != 1 or model.njnt != 1 or model.jnt_type[0] != mujoco.mjtJoint.mjJNT_SLIDE:
            raise EvidenceError('This replay adapter supports the verified single slide model only')
        def name(kind, i):
            return mujoco.mj_id2name(model,kind,i) or f'{kind.name}_{i}'
        bodies = [{'id':f'body:{i}','name':name(mujoco.mjtObj.mjOBJ_BODY,i),'kind':'body',
                   'parent':int(model.body_parentid[i]),'position':data.xpos[i].tolist(),
                   'quaternion_wxyz':data.xquat[i].tolist(),'mass_kg':float(model.body_mass[i])}
                  for i in range(model.nbody)]
        geoms=[]
        for i in range(model.ngeom):
            body = int(model.geom_bodyid[i]); ancestor = body; moving=False
            while ancestor:
                moving = moving or int(model.body_jntnum[ancestor]) > 0
                ancestor = int(model.body_parentid[ancestor])
            quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[i])
            geoms.append({'id':f'geom:{i}','name':name(mujoco.mjtObj.mjOBJ_GEOM,i),'kind':'geom',
                'body':body,'type':int(model.geom_type[i]),'size':model.geom_size[i].tolist(),
                'position':data.geom_xpos[i].tolist(),'quaternion_wxyz':quat.tolist(),
                'rgba':model.geom_rgba[i].tolist(),'moving':moving,
                'collision':bool(model.geom_contype[i] or model.geom_conaffinity[i])})
        joints=[{'id':f'joint:{i}','name':name(mujoco.mjtObj.mjOBJ_JOINT,i),'kind':'joint',
                 'body':int(model.jnt_bodyid[i]),'axis':model.jnt_axis[i].tolist(),
                 'position':data.xanchor[i].tolist(),'limited':bool(model.jnt_limited[i]),
                 'range':model.jnt_range[i].tolist() if model.jnt_limited[i] else None}
                for i in range(model.njnt)]
        actuators=[{'id':f'actuator:{i}','name':name(mujoco.mjtObj.mjOBJ_ACTUATOR,i),'kind':'actuator',
                    'joint':int(model.actuator_trnid[i,0]),'gear':model.actuator_gear[i].tolist(),
                    'force_range_n':model.actuator_forcerange[i].tolist(),
                    'control_range':model.actuator_ctrlrange[i].tolist()} for i in range(model.nu)]
        axis=data.xaxis[0].copy()
        # Independently check the frontend's rigid translation for EVERY sample.
        # This is kinematics of recorded states, never a new solver/safety result.
        for trajectory in trajectories.values():
            for sample in trajectory['samples']:
                data.qpos[0],data.qvel[0]=sample['position'],sample['velocity']
                mujoco.mj_forward(model,data)
                for i,g in enumerate(geoms):
                    expected=np.array(g['position']) + (axis*(sample['position']-first['position']) if g['moving'] else 0)
                    if not np.allclose(expected,data.geom_xpos[i],rtol=0,atol=1e-12):
                        raise EvidenceError('Recorded transform synchronization failed')
        output={}
        for variant,t in trajectories.items():
            samples=t['samples']; markers=[]
            for label,predicate in [('Braking begins',lambda s:abs(s['generalized_actuator_force'])>1e-9),
                                    ('First contact',lambda s:s['wall_collision']),
                                    ('Clearance violation',lambda s:s['wall_clearance']<context['minimum_clearance_m'])]:
                index=next((i for i,s in enumerate(samples) if predicate(s)),None)
                if index is not None:markers.append({'label':label,'index':index,'time':samples[index]['time']})
            markers.append({'label':'End','index':len(samples)-1,'time':samples[-1]['time']})
            output[variant]={'samples':samples,'summary':t['summary'],'independent':t['independent'],
                             'markers':markers,'telemetry_reference':t['telemetry_reference']}
        return {'scenario':scenario,'provenance':'RECORDED — Day 4B.2; not live simulation',
                'inventory_sha256':self.recording.inventory_sha256,'context':context,'variants':output,
                'scene':{'bodies':bodies,'geoms':geoms,'joints':joints,'actuators':actuators,
                         'slide_axis_world':axis.tolist(),'reference_position':first['position'],
                         'transform_check':'All recorded samples checked against MuJoCo mj_forward (1e-12)'}}

    def recorded_agent(self):
        return {'mode':'recorded','calls':self.recording.tool_trace(),
                'diagnosis':self.recording.read('model_diagnosis.txt').decode(),
                'result':self.recording.json('session/session_result.json')}

    def review(self, body, *, family='rail'):
        if family=='arm':
            if set(body)=={'variant'}:
                p=self.arm_recording().proposal(body['variant'])
                return self.arm_workflow.create(source=p['source'],explanation=p['validation']['explanation'],
                    expected_original_sha256=p['validation']['original_sha256'],provenance=p['provenance'])
            if set(body)=={'source','explanation','expected_original_sha256'} and all(isinstance(v,str) for v in body.values()):
                return self.arm_workflow.create(source=body['source'],explanation=body['explanation'],
                    expected_original_sha256=body['expected_original_sha256'],provenance={'kind':'manual_editor_draft','ai_generated':False})
            raise ValueError('Unknown arm review request')
        if set(body)=={'variant'} and body['variant'] in VARIANTS[1:]:
            p=self.recording.proposal(body['variant'])
            return self.workflow.create(source=p['source'],explanation=p['validation']['explanation'],
                expected_original_sha256=p['validation']['original_sha256'],
                provenance={'kind':'recorded_genuine_model_proposal','recording':self.recording.inventory_sha256,**p['provenance']})
        if set(body)=={'source','explanation','expected_original_sha256'} and all(isinstance(v,str) for v in body.values()):
            return self.workflow.create(source=body['source'],explanation=body['explanation'],
                expected_original_sha256=body['expected_original_sha256'],provenance={'kind':'manual_editor_draft','ai_generated':False})
        raise ValueError('Review requires a known recorded proposal or explicit controller draft fields')

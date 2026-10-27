"""Pinned multi-DOF evidence adapter. Data-only review; no source execution."""
import difflib
import hashlib
import json
from pathlib import Path
import mujoco
import numpy as np
from core.simulation import ROOT
from core.agent.patching import read_project_file
from core.robots.arm import ArmFamily,TARGET,MODEL,CONFIG,EVALUATION
from workspace.data import bounded_read,decode_json,EvidenceError


class ArmRecording:
    def __init__(self,root,index_path,index_sha256):
        self.root=Path(root).absolute();raw=bounded_read(self.root,index_path)
        if hashlib.sha256(raw).hexdigest()!=index_sha256:raise EvidenceError('Arm recording index hash mismatch')
        self.index=decode_json(raw);self.identity=index_sha256
        if self.index.get('robot_family')!='arm':raise EvidenceError('Wrong recorded robot family')
        expected=self.index.get('project_hashes',{})
        if set(expected)!={TARGET,MODEL,CONFIG,EVALUATION}:raise EvidenceError('Missing arm project identities')
        if any(read_project_file(ROOT,p,set(expected))['sha256']!=sha for p,sha in expected.items()):
            raise EvidenceError('Arm project differs from the pinned recording')

    def reference(self,path):
        if str(path) in self.index['files']:return str(path)
        p=Path(path);p=p if p.is_absolute() else ROOT/p
        try:return p.relative_to(self.root).as_posix()
        except ValueError as exc:raise EvidenceError('Arm evidence reference escaped recording') from exc

    def read(self,path):
        relative=self.reference(path)
        if relative not in self.index['files']:raise EvidenceError('Arm file is not indexed')
        raw=bounded_read(self.root,relative)
        if hashlib.sha256(raw).hexdigest()!=self.index['files'][relative]:raise EvidenceError('Arm evidence file hash mismatch')
        return raw

    def json(self,path):return decode_json(self.read(path))

    def proposal(self,variant):
        if variant not in self.index['proposals']:raise EvidenceError('Unknown arm proposal')
        refs=self.index['proposals'][variant];source=self.read(refs['source']).decode();v=self.json(refs['validation'])
        original=read_project_file(ROOT,TARGET,{TARGET})
        diff=''.join(difflib.unified_diff(original['content'].splitlines(True),source.splitlines(True),fromfile=TARGET,tofile='candidate/'+TARGET))
        if (hashlib.sha256(source.encode()).hexdigest()!=v['proposed_sha256'] or original['sha256']!=v['original_sha256']
                or diff!=v['unified_diff'] or self.read(refs['diff']).decode()!=diff):
            raise EvidenceError('Arm proposal source/diff identity mismatch')
        return {'source':source,'diff':diff,'validation':v,'verification':self.json(refs['verification']),
                'provenance':self.json(refs['provenance'])}

    def metadata(self):
        return {'recorded':True,'robot_family':'arm','inventory_sha256':self.identity,
                'scenarios':list(self.index['scenarios']),'proposals':list(self.index['proposals']),
                'agent':self.agent(),'files':[{'path':p,'historical':False} for p in sorted(ArmFamily.read_allowlist)]}

    def agent(self):
        if not self.index.get('agent'):return {'status':'NOT_RUN','calls':[],'diagnosis':'No genuine arm model session is recorded in this index.'}
        refs=self.index['agent'];events=[decode_json(row) for row in self.read(refs['trace']).splitlines() if row];calls=[]
        for event in events:
            payload=event['payload']
            if event['event']=='tool_requested':calls.append({'name':payload['name'],'arguments':payload['arguments']})
            elif event['event']=='tool_completed':
                if not calls or calls[-1]['name']!=payload['name']:raise EvidenceError('Arm trace order mismatch')
                calls[-1]['output']=payload['output']
            elif event['event']=='candidate_verification' and calls:calls[-1]['verification_feedback']=payload
        result=self.json(refs['result'])
        task=next((e['payload']['text'] for e in events if e['event']=='user_request'),'Recorded task unavailable')
        return {'status':result['orchestration_status'],'calls':calls,'diagnosis':result['model_final_text'],
                'task':task,'result':result,'label':'RECORDED genuine API session, not live inference'}

    def experiment(self,scenario):
        if scenario not in self.index['scenarios']:raise EvidenceError('Unknown recorded arm scenario')
        family=ArmFamily(evaluation=True);variants={};scene=None;context=None
        for variant,summary_path in self.index['scenarios'][scenario].items():
            summary=self.json(summary_path)
            if summary['scenario_id']!=scenario:raise EvidenceError('Arm scenario identity mismatch')
            if summary['simulation_execution']=='NOT_RUN':
                variants[variant]={'summary':summary,'samples':[]};context=family.context(scenario);continue
            telemetry=self.json(summary['artifact_references']['telemetry.json'])
            meta=telemetry['metadata'];samples=telemetry['samples'];xml=self.read(summary['artifact_references']['effective_model.xml']).decode()
            _,current,c,body,world,_=family.compile(scenario,summary['controller_sha256'])
            if (xml!=current or hashlib.sha256(xml.encode()).hexdigest()!=meta['effective_mjcf_sha256']
                    or c.identity!=meta['contract_sha256'] or c.to_dict()!=meta['physics_contract']
                    or meta['controller_sha256']!=summary['controller_sha256']):
                raise EvidenceError('Current arm context/source differs from recorded evidence')
            expected_source=(read_project_file(ROOT,TARGET,{TARGET})['sha256'] if variant=='original'
                             else self.proposal(variant)['validation']['proposed_sha256'])
            if expected_source!=summary['controller_sha256']:raise EvidenceError('Arm controller identity mismatch')
            check=self.json(summary['artifact_references']['independent.json'])
            if check['verification_execution']!=summary['independent_verification'] or check['safety_acceptance']!=summary['safety_acceptance']:
                raise EvidenceError('Arm independent result identity mismatch')
            model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
            if len(samples)!=round(c.duration_s/c.timestep_s)+1:raise EvidenceError('Arm trajectory is incomplete')
            for k,s in enumerate(samples):
                if (len(s['qpos_rad'])!=2 or len(s['qvel_rad_s'])!=2 or not np.isfinite(s['qpos_rad']+s['qvel_rad_s']).all()
                        or abs(s['time']-k*c.timestep_s)>1e-10 or len(s['geom_poses'])!=model.ngeom):
                    raise EvidenceError('Invalid arm trajectory state/grid')
                data.qpos[:]=s['qpos_rad'];data.qvel[:]=s['qvel_rad_s'];mujoco.mj_forward(model,data)
                for i,pose in enumerate(s['geom_poses']):
                    quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[i])
                    if not np.allclose(data.geom_xpos[i],pose['position'],rtol=0,atol=1e-10) or not np.allclose(quat,pose['quaternion_wxyz'],rtol=0,atol=1e-10):
                        raise EvidenceError('Recorded articulated pose does not match compiled MuJoCo kinematics')
                if not np.allclose(data.site_xpos[model.site('end_effector').id],s['end_effector_m'],rtol=0,atol=1e-10):
                    raise EvidenceError('Recorded arm endpoint mismatch')
            if scene is None:
                data.qpos[:]=samples[0]['qpos_rad'];mujoco.mj_forward(model,data)
                geoms=[]
                for i in range(model.ngeom):
                    quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[i])
                    geoms.append({'id':f'geom:{i}','name':model.geom(i).name,'kind':'geom','body':int(model.geom_bodyid[i]),
                         'type':int(model.geom_type[i]),'size':model.geom_size[i].tolist(),'rgba':model.geom_rgba[i].tolist(),
                         'position':data.geom_xpos[i].tolist(),'quaternion_wxyz':quat.tolist(),'moving':bool(model.body_jntnum[model.geom_bodyid[i]])})
                scene={'family':'arm','geoms':geoms,
                       'bodies':[{'id':f'body:{i}','name':model.body(i).name,'kind':'body','mass_kg':float(model.body_mass[i]),'position':data.xpos[i].tolist()} for i in range(1,model.nbody)],
                       'joints':[{'id':f'joint:{i}','name':model.joint(i).name,'kind':'joint','range':model.jnt_range[i].tolist(),'axis':model.jnt_axis[i].tolist()} for i in range(model.njnt)],
                       'actuators':[{'id':f'actuator:{i}','name':model.actuator(i).name,'kind':'actuator','torque_range_nm':model.actuator_forcerange[i].tolist()} for i in range(model.nu)],
                       'reference_position':0,'slide_axis_world':[0,0,0],
                       'transform_check':'All recorded geom positions AND rotations independently checked against compiled MuJoCo states.'}
                context={'bodybase':body,'worldbase':world,'contract':c.to_dict(),'analytical_guard':summary['analytical_guard']}
            variants[variant]={'summary':summary,'samples':samples,'independent':{k:v for k,v in check.items() if k!='trace'}}
        return {'scenario':scenario,'robot_family':'arm','recorded':True,'provenance':'RECORDED real MuJoCo states; no new simulation',
                'inventory_sha256':self.identity,'scene':scene,'context':context,'variants':variants}


def default_arm_recording():
    config=decode_json(bounded_read(ROOT/'workspace','arm_recording.json'))
    if not isinstance(config.get('root'),str) or not config['root'].startswith('artifacts/day9/'):
        raise EvidenceError('Arm recording root is not authorized')
    # The root is subsequently walked with no-follow file descriptors.
    parts=config['root'].split('/')
    if any(p in ('','.','..') for p in parts):raise EvidenceError('Invalid arm recording root')
    return ArmRecording(ROOT/config['root'],config['index'],config['index_sha256'])

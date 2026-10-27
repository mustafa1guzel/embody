"""Restricted trusted scene -> deterministic MJCF; independent native probes."""
import hashlib
from xml.etree.ElementTree import Element,SubElement,tostring
import mujoco
import numpy as np
from .schema import validate,identity
from physics.contracts import digest


def numbers(v):return ' '.join(format(float(x),'.17g') for x in v)

def geometry_size(o):
    x,y,z=o['dimensions_m'];g=o['geometry']
    return [x/2,y/2,z/2] if g in ('box','plane') else [x/2] if g=='sphere' else [x/2,z/2] if g=='cylinder' else [x/2,(z-x)/2]


def compile_world(world):
    w=validate(world);root=Element('mujoco',model=w['id']);SubElement(root,'compiler',angle='radian',eulerseq='XYZ',inertiafromgeom='true')
    SubElement(root,'option',timestep='.005',gravity=numbers(w['environment']['gravity_m_s2']),integrator='Euler')
    visual=SubElement(root,'visual');SubElement(visual,'global',offwidth='640',offheight='480')
    wb=SubElement(root,'worldbody');SubElement(wb,'light',pos='0 -2 4');act=SubElement(root,'actuator');sensors=SubElement(root,'sensor')
    children={}
    for o in w['objects']:children.setdefault(o['parent'],[]).append(o)
    def add(parent,parent_id):
        for o in sorted(children.get(parent_id,[]),key=lambda o:o['id']):
            body=SubElement(parent,'body',name=o['id'],pos=numbers(o['position_m']),euler=numbers(o['rotation_rad']))
            j=o['joint']
            if j:
                if j['kind']=='free':SubElement(body,'freejoint',name='joint_'+o['id'])
                else:
                    SubElement(body,'joint',name='joint_'+o['id'],type='hinge' if j['kind']=='revolute' else 'slide',axis=numbers(j['axis']),limited='true',range=numbers(j['range']),damping=str(j['damping']))
                    for tag in ('jointpos','jointvel'):SubElement(sensors,tag,name=tag+'_'+o['id'],joint='joint_'+o['id'])
            kwargs={'name':'geom_'+o['id'],'type':o['geometry'],'size':numbers(geometry_size(o)),'rgba':numbers(o['visual']['rgba']),'friction':numbers(o['contact']['friction']),'contype':'1' if o['contact']['enabled'] else '0','conaffinity':'1' if o['contact']['enabled'] else '0'}
            kwargs['mass']=str(o['mass_kg'])
            SubElement(body,'geom',**kwargs)
            if o['actuator']:
                a=o['actuator'];SubElement(act,'motor',name='motor_'+o['id'],joint='joint_'+o['id'],gear='1',ctrllimited='true',ctrlrange=numbers([-a['limit'],a['limit']]),forcelimited='true',forcerange=numbers([-a['limit'],a['limit']]))
            add(body,o['id'])
    add(wb,None);xml=tostring(root,encoding='unicode');model=mujoco.MjModel.from_xml_string(xml)
    data=initial_state(model,w);mujoco.mj_forward(model,data)
    compiled=[];probes=[]
    for o in w['objects']:
        b=model.body(o['id']);g=model.geom('geom_'+o['id']);size=geometry_size(o)
        np.testing.assert_allclose(g.size[:len(size)],size,rtol=0,atol=1e-12)
        np.testing.assert_allclose(model.body_pos[b.id],o['position_m'],rtol=0,atol=1e-12)
        if o['kind'] in ('dynamic','link'):
            np.testing.assert_allclose(b.mass,[o['mass_kg']],rtol=1e-12,atol=1e-12)
            if o['geometry']=='box':
                x,y,z=o['dimensions_m'];expected=o['mass_kg']/12*np.array([y*y+z*z,x*x+z*z,x*x+y*y])
                np.testing.assert_allclose(np.sort(b.inertia),np.sort(expected),rtol=1e-12,atol=1e-14)
            if o['geometry']=='cylinder':
                radius,height=o['dimensions_m'][0]/2,o['dimensions_m'][2]
                expected=o['mass_kg']/12*np.array([3*radius**2+height**2,3*radius**2+height**2,6*radius**2])
                np.testing.assert_allclose(np.sort(b.inertia),np.sort(expected),rtol=1e-12,atol=1e-14)
        if o['joint'] and o['joint']['kind']!='free':np.testing.assert_allclose(model.joint('joint_'+o['id']).range,o['joint']['range'],atol=1e-12,rtol=0)
        if o['actuator']:
            a=model.actuator('motor_'+o['id']);jid=int(model.actuator_trnid[a.id,0]);dof=int(model.jnt_dofadr[jid])
            for command in (-1000.,0.,1000.):
                data.ctrl[:]=0;data.ctrl[a.id]=command;mujoco.mj_forward(model,data)
                expected=float(np.clip(command,-o['actuator']['limit'],o['actuator']['limit']))
                np.testing.assert_allclose([data.actuator_force[a.id],data.qfrc_actuator[dof]],[expected,expected],atol=1e-12,rtol=0)
                probes.append({'object':o['id'],'request':command,'actuator_force':float(data.actuator_force[a.id]),'generalized_force':float(data.qfrc_actuator[dof]),'unit':o['actuator']['unit']})
        compiled.append({'id':o['id'],'mass_kg':float(b.mass[0]),'inertia_kg_m2':b.inertia.tolist(),'local_position_m':model.body_pos[b.id].tolist(),'world_position_m':data.geom_xpos[g.id].tolist(),'size_mujoco':g.size.tolist()})
    contract={'schema_version':1,'world_sha256':identity(w),'model_sha256':hashlib.sha256(xml.encode()).hexdigest(),'units':'SI','compiler_sha256':hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),'duration_s':w['environment']['duration_s'],'controls':'Frozen constant bounded motor requests; no source execution','sensors':['native joint position','native joint velocity'],'unsupported':w['unsupported']}
    return model,xml,{'contract':contract,'contract_sha256':digest(contract),'compiled':compiled,'force_probes':probes,'warnings':w['unsupported']}


def initial_state(model,w):
    data=mujoco.MjData(model)
    for o in w['objects']:
        j=o['joint']
        if j and j['kind']!='free':
            joint=model.joint('joint_'+o['id']);data.qpos[joint.qposadr[0]]=j['initial_position'];data.qvel[joint.dofadr[0]]=j['initial_velocity']
    return data

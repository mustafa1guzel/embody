"""New editable-schema experiments; criteria are frozen separately before runs."""
from .objects import empty_world,primitive


def obstacle(wall_x=.7):
    w=empty_world();w['environment'].update(gravity_m_s2=[0.,0.,0.],duration_s=1.5)
    body=primitive('prismatic','carriage');body.update(position_m=[0.,0.,.2],dimensions_m=[.1,.1,.1]);body['joint'].update(axis=[1.,0.,0.],range=[-.1,2.],initial_velocity=1.,damping=0.)
    wall=primitive('obstacle','wall');wall.update(position_m=[wall_x,0.,.25],dimensions_m=[.1,.5,.5])
    w['objects'] += [body,wall];return w


def motor(mass=.8,limit=.005):
    w=empty_world();w['environment'].update(gravity_m_s2=[0.,0.,0.],duration_s=.5)
    link=primitive('motor','beam');link.update(position_m=[0.,0.,.5],dimensions_m=[.4,.04,.04],mass_kg=mass);link['joint'].update(range=[0.,2.],axis=[0.,0.,1.],damping=.01);link['actuator'].update(limit=limit,command=limit);link['contact']['enabled']=False
    w['objects'].append(link);return w


def assembly():
    w=empty_world();w['environment'].update(gravity_m_s2=[0.,0.,0.],duration_s=.5)
    anchor=primitive('anchor','base');anchor['position_m']=[0.,0.,.6]
    one=primitive('motor','link_one');one.update(parent='base',position_m=[0.,0.,0.],dimensions_m=[.3,.03,.03]);one['actuator'].update(limit=.1,command=.02);one['contact']['enabled']=False
    two=primitive('motor','link_two');two.update(parent='link_one',position_m=[.3,0.,0.],dimensions_m=[.25,.03,.03]);two['actuator'].update(limit=.1,command=.015);two['contact']['enabled']=False
    w['objects'] += [anchor,one,two];return w

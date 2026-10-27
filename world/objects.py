"""Trusted primitive defaults. Dimensions are full extents, Z is cylinder axis."""
from uuid import uuid4
from .schema import validate

LIBRARY=('box','sphere','cylinder','capsule','floor','anchor','rigid_link','revolute','prismatic','motor','obstacle','dynamic_body')


def primitive(kind,identifier=None):
    if kind not in LIBRARY:raise ValueError('Unsupported world primitive')
    o={'id':identifier or 'object_'+uuid4().hex,'name':kind.replace('_',' ').title(),'parent':None,'kind':'static','geometry':'box','position_m':[0.,0.,.15],'rotation_rad':[0.,0.,0.],'dimensions_m':[.2,.1,.1],'mass_kg':0.,'joint':None,'actuator':None,'contact':{'enabled':True,'friction':[.7,.005,.0001]},'visual':{'rgba':[.35,.58,.67,1.],'material':'illustrative_solid'}}
    if kind in ('sphere','cylinder','capsule'):o['geometry']=kind;o['dimensions_m']=[.1,.1,.1 if kind=='sphere' else .3]
    if kind=='floor':o.update(geometry='plane',name='Floor',position_m=[0.,0.,0.],dimensions_m=[4.,4.,.1])
    if kind=='anchor':o.update(kind='anchor',dimensions_m=[.08,.08,.08])
    if kind=='obstacle':o.update(kind='obstacle',name='Obstacle')
    if kind in ('rigid_link','revolute','prismatic','motor','dynamic_body'):
        o.update(kind='link' if kind=='rigid_link' else 'dynamic',mass_kg=.2)
        joint='prismatic' if kind=='prismatic' else 'free' if kind=='dynamic_body' else 'revolute'
        o['joint']={'kind':joint,'axis':[0.,0.,1.],'range':[-1,1],'initial_position':0.,'initial_velocity':0.,'damping':0. if joint=='free' else .01}
        if kind=='motor':o['actuator']={'limit':.2,'command':.1,'unit':'N*m'}
    return o


def empty_world():
    return {'schema_version':1,'id':'world_main','revision':0,'units':'SI','objects':[primitive('floor','floor')],'environment':{'gravity_m_s2':[0.,0.,-9.81],'timestep_s':.005,'duration_s':2.},'unsupported':['Deformable bodies, mesh assets, arbitrary MJCF, fluid/thermal/electrical dynamics and user code are unsupported.','Contacts and joint limits are compliant MuJoCo constraints, not rigid safety guarantees.']}

"""Bounded SI scene document. No MJCF, assets, expressions or executable fields."""
import copy, math
from jsonschema import Draft202012Validator
from physics.contracts import digest


def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
def num(lo,hi):return {'type':'number','minimum':lo,'maximum':hi}
def vec(lo,hi):return {'type':'array','items':num(lo,hi),'minItems':3,'maxItems':3}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_]{0,47}$','maxLength':48}
JOINT=obj({'kind':{'enum':['revolute','prismatic','free']},'axis':vec(-1,1),'range':{'type':'array','items':num(-10,10),'minItems':2,'maxItems':2},'initial_position':num(-10,10),'initial_velocity':num(-5,5),'damping':num(0,10)})
MOTOR=obj({'limit':num(.001,100),'command':num(-100,100),'unit':{'enum':['N','N*m']}})
OBJECT=obj({'id':ID,'name':{'type':'string','minLength':1,'maxLength':80},'parent':{'anyOf':[ID,{'type':'null'}]},'kind':{'enum':['static','dynamic','anchor','link','obstacle']},'geometry':{'enum':['box','sphere','cylinder','capsule','plane']},'position_m':vec(-10,10),'rotation_rad':vec(-math.tau,math.tau),'dimensions_m':vec(.005,5),'mass_kg':num(0,100),'joint':{'anyOf':[JOINT,{'type':'null'}]},'actuator':{'anyOf':[MOTOR,{'type':'null'}]},'contact':obj({'enabled':{'type':'boolean'},'friction':vec(0,5)}),'visual':obj({'rgba':{'type':'array','items':num(0,1),'minItems':4,'maxItems':4},'material':{'enum':['illustrative_solid']}})})
WORLD=obj({'schema_version':{'const':1},'id':ID,'revision':{'type':'integer','minimum':0,'maximum':999999},'units':{'const':'SI'},'objects':{'type':'array','items':OBJECT,'maxItems':48},'environment':obj({'gravity_m_s2':vec(-20,20),'timestep_s':{'const':.005},'duration_s':num(.05,5)}),'unsupported':{'type':'array','items':{'type':'string','maxLength':160},'maxItems':16}})


def validate(value):
    import json
    raw=json.dumps(value,allow_nan=False).encode()
    if len(raw)>100000:raise ValueError('World exceeds 100000 bytes')
    errors=list(Draft202012Validator(WORLD).iter_errors(value))
    if errors:raise ValueError('Invalid world '+'.'.join(map(str,errors[0].absolute_path))+': '+errors[0].message[:160])
    # jsonschema treats integral floats as integers; engineering revisions do not.
    if type(value['revision']) is not int or type(value['schema_version']) is not int:raise ValueError('Integer world version/revision required')
    ids={o['id']:o for o in value['objects']}
    if len(ids)!=len(value['objects']):raise ValueError('Duplicate object identity')
    joints=motors=0
    for o in value['objects']:
        parent=o['parent'];seen={o['id']}
        while parent is not None:
            if parent not in ids or parent in seen:raise ValueError('Absent parent or cyclic hierarchy')
            seen.add(parent);parent=ids[parent]['parent']
        moving=o['kind'] in ('dynamic','link')
        if moving and o['mass_kg']<.001:raise ValueError('Dynamic body mass must be at least .001 kg')
        if not moving and (o['mass_kg']!=0 or o['joint'] or o['actuator']):raise ValueError('Static objects have zero mass and no joint/actuator')
        if o['parent'] and not moving and any(ids[k]['kind'] in ('dynamic','link') for k in seen-{o['id']}):raise ValueError('Static child on moving body unsupported; use a rigid link')
        if o['geometry']=='plane' and (moving or o['parent'] is not None):raise ValueError('Plane is static world-root only')
        d=o['dimensions_m']
        if o['geometry']=='sphere' and not d[0]==d[1]==d[2]:raise ValueError('Sphere requires equal diameters')
        if o['geometry'] in ('cylinder','capsule') and d[0]!=d[1]:raise ValueError('Circular geometry requires equal X/Y diameters')
        if o['geometry']=='capsule' and d[2]<=d[0]:raise ValueError('Capsule height must exceed diameter')
        j=o['joint']
        if moving and not j and (o['parent'] is None or ids[o['parent']]['kind'] not in ('dynamic','link')):raise ValueError('Moving root requires a joint; fixed links require moving parent')
        if j:
            joints+=1
            if abs(sum(x*x for x in j['axis'])-1)>1e-10:raise ValueError('Joint axis must be unit length')
            lo,hi=j['range']
            if lo>=hi or not lo<=j['initial_position']<=hi:raise ValueError('Invalid joint range/initial position')
            if j['kind']=='revolute' and (lo < -math.pi or hi > math.pi):raise ValueError('Revolute range outside +/- pi')
            if j['kind']=='prismatic' and (lo < -2 or hi > 2):raise ValueError('Prismatic range outside +/- 2 m')
            if j['kind']=='free' and (o['parent'] is not None or o['actuator'] or j['initial_position'] or j['initial_velocity'] or j['range']!=[-1,1] or j['damping']!=0):raise ValueError('Free bodies only at root, no motor or scalar initial state; range is unused [-1,1]')
        if o['actuator']:
            motors+=1;a=o['actuator']
            if not j or j['kind']=='free' or a['unit']!=('N*m' if j['kind']=='revolute' else 'N') or abs(a['command'])>a['limit']:raise ValueError('Motor requires bounded scalar joint and correct SI unit')
    if joints>24 or motors>16:raise ValueError('Joint/actuator count limit')
    return copy.deepcopy(value)


def identity(value):return digest(validate(value))

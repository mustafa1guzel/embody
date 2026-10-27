"""Strict versioned graph data; layout never implies connectivity."""
import copy
import math
import re
from uuid import uuid4
import numpy as np
from physics.contracts import digest
from .library import CATALOG, catalog_hash, pin

ID = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')


def fields(value, expected):
    if not isinstance(value,dict) or set(value)!=set(expected):
        raise ValueError('Unexpected schema fields: '+str(expected))


def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('Invalid stable identifier')
    return value


def vector(value, bound):
    if not isinstance(value,list) or len(value)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>bound for x in value):
        raise ValueError('Invalid finite bounded transform')


def validate(a):
    fields(a,['schema_version','id','revision','catalog_sha256','components','nets','wires'])
    if type(a['schema_version']) is not int or a['schema_version']!=1 or a['catalog_sha256']!=catalog_hash():raise ValueError('Unsupported schema or stale catalog')
    identifier(a['id'])
    if type(a['revision']) is not int or not 0<=a['revision']<1_000_000:raise ValueError('Invalid assembly revision')
    for name,maximum in [('components',64),('nets',128),('wires',256)]:
        if not isinstance(a[name],list) or len(a[name])>maximum:raise ValueError('Assembly size limit')
    ids={};nets=set();wireids=set();membership={};adj={}
    for c in a['components']:
        fields(c,['id','part','name','parent','position_m','rotation_rad','roles']);identifier(c['id'])
        if c['id'] in ids or c['part'] not in CATALOG:raise ValueError('Duplicate component or unknown part')
        if not isinstance(c['name'],str) or not 0<len(c['name'])<=100:raise ValueError('Invalid component name')
        if c['parent']!=a['id']:raise ValueError('Unknown parent assembly')
        vector(c['position_m'],10);vector(c['rotation_rad'],math.tau*10)
        if not isinstance(c['roles'],dict):raise ValueError('Invalid pin roles')
        for p,role in c['roles'].items():
            spec=pin(c['part'],p)
            if not spec or spec.role!='configurable' or role not in ('input','output','pwm'):raise ValueError('Invalid configurable pin role')
        ids[c['id']]=c
    for n in a['nets']:
        fields(n,['id','name']);identifier(n['id'])
        if n['id'] in nets or not isinstance(n['name'],str) or not 0<len(n['name'])<=100:raise ValueError('Invalid net')
        nets.add(n['id']);adj[n['id']]={}
    for w in a['wires']:
        fields(w,['id','net','a','b']);identifier(w['id'])
        if w['id'] in wireids or w['net'] not in nets:raise ValueError('Duplicate wire or absent net')
        wireids.add(w['id']);ends=[]
        for endpoint in (w['a'],w['b']):
            fields(endpoint,['component','pin']);key=(endpoint['component'],endpoint['pin'])
            if key[0] not in ids or not pin(ids[key[0]]['part'],key[1]):raise ValueError('Wire references absent pin')
            if key in membership and membership[key]!=w['net']:raise ValueError('One pin cannot belong to two nets')
            membership[key]=w['net'];ends.append(key);adj[w['net']].setdefault(key,set())
        if ends[0]==ends[1]:raise ValueError('Self wire')
        adj[w['net']][ends[0]].add(ends[1]);adj[w['net']][ends[1]].add(ends[0])
    for graph in adj.values():
        if not graph:raise ValueError('Empty net')
        seen=set();stack=[next(iter(graph))]
        while stack:
            key=stack.pop()
            if key not in seen:seen.add(key);stack.extend(graph[key]-seen)
        if len(seen)!=len(graph):raise ValueError('A net must have explicit connected wire edges')
    return copy.deepcopy(a)


def empty():
    return {'schema_version':1,'id':'assembly_'+uuid4().hex,'revision':0,'catalog_sha256':catalog_hash(),'components':[],'nets':[],'wires':[]}


def instance(a, part, name=None, identifier_=None, position=None):
    if part not in CATALOG:raise ValueError('Unknown component')
    return {'id':identifier_ or 'part_'+uuid4().hex,'part':part,'name':name or CATALOG[part].model,'parent':a['id'],
            'position_m':position or [0.,0.,0.],'rotation_rad':[0.,0.,0.],'roles':{}}


def endpoint(component, p):return {'component':component,'pin':p}


def connect(a, first, second):
    result=copy.deepcopy(a)
    attached={}
    for w in result['wires']:
        for e in (w['a'],w['b']):attached[(e['component'],e['pin'])]=w['net']
    keys=[(e['component'],e['pin']) for e in (first,second)]
    existing=[attached[k] for k in keys if k in attached]
    net=existing[0] if existing else 'net_'+uuid4().hex
    if not existing:result['nets'].append({'id':net,'name':net})
    for w in result['wires']:
        if w['net'] in existing:w['net']=net
    result['nets']=[n for n in result['nets'] if n['id'] not in existing or n['id']==net]
    result['wires'].append({'id':'wire_'+uuid4().hex,'net':net,'a':first,'b':second})
    result['revision']+=1
    return validate(result)


def remove_wire(a, wire_id):
    """Split disconnected nets after removal, preserving old identity for first group."""
    result=copy.deepcopy(a)
    if wire_id not in {w['id'] for w in a['wires']}:raise ValueError('Unknown wire')
    result['wires']=[w for w in result['wires'] if w['id']!=wire_id]
    oldnets=result['nets'];result['nets']=[]
    for n in oldnets:
        remaining=[w for w in result['wires'] if w['net']==n['id']];group=0
        while remaining:
            members={(remaining[0][e]['component'],remaining[0][e]['pin']) for e in ('a','b')};chosen=[]
            changed=True
            while changed:
                changed=False
                for w in list(remaining):
                    ends={(w[e]['component'],w[e]['pin']) for e in ('a','b')}
                    if ends & members:members|=ends;chosen.append(w);remaining.remove(w);changed=True
            new=n['id'] if group==0 else 'net_'+uuid4().hex
            result['nets'].append({'id':new,'name':n['name'] if group==0 else n['name']+' split'})
            for w in chosen:w['net']=new
            group+=1
    result['revision']+=1
    return validate(result)


def netlist(a):
    validate(a);result={n['id']:set() for n in a['nets']}
    for w in a['wires']:
        for e in (w['a'],w['b']):result[w['net']].add((e['component'],e['pin']))
    return {n:sorted(values) for n,values in result.items()}


def endpoint_position(a, e):
    c=next(c for c in a['components'] if c['id']==e['component']);v=np.array(pin(c['part'],e['pin']).position_m)
    x,y,z=c['rotation_rad'];cx,sx,cy,sy,cz,sz=math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    # Three Euler XYZ convention: R = Rx Ry Rz.
    rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]]);ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]]);rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    return (np.array(c['position_m'])+rx@ry@rz@v).tolist()


def identity(a):return digest(validate(a))

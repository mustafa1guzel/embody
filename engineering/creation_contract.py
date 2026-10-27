"""Bounded creation metadata; geometry-only concepts never acquire fake pins."""
from jsonschema import Draft202012Validator
from world.schema import obj,ID,num

TEXT={'type':'string','minLength':1,'maxLength':1000}
TEXTS={'type':'array','items':TEXT,'maxItems':32}
ROLES={'type':'object','propertyNames':ID,'additionalProperties':ID,'maxProperties':48}
CREATION=obj({'family':{'enum':['sensor_barrier','smart_glasses']},'state':{'enum':['EMPTY','BUILT']},'plan_id':ID,'request_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'template_version':{'const':'day16_v1'},'origin':{'const':'DETERMINISTIC_OFFLINE; not live AI synthesis'},'world_roles':ROLES,'component_roles':ROLES,'controller_family':{'enum':['NONE','TRUSTED_BARRIER_V1']},'mounts':{'type':'array','maxItems':8,'items':obj({'component':ID,'world_object':ID,'kind':{'enum':['GEOMETRIC_SENSOR','VISUAL_ONLY']},'electronic_mass_included':{'const':False}})},'concept_envelopes':{'type':'array','maxItems':24,'items':obj({'world_object':ID,'subsystem':TEXT,'assumed_mass_kg':num(0,.1),'capability':{'const':'GEOMETRY_ONLY'},'verified_functionality':{'const':False}})},'dependencies':{'type':'array','maxItems':48,'items':obj({'source':ID,'target':ID,'kind':{'const':'PLANNING_ONLY'}})},'capabilities':TEXTS,'unsupported':TEXTS,'empty_project_sha256':{'anyOf':[{'type':'null'},{'type':'string','pattern':'^[0-9a-f]{64}$'}]}})

def validate_creation(p):
    m=p['creation']
    if not Draft202012Validator(CREATION).is_valid(m):raise ValueError('Invalid creation metadata')
    worlds={o['id'] for o in p['world']['objects']};components={o['id'] for o in p['circuit']['components']}
    if not set(m['world_roles'].values())<=worlds or not set(m['component_roles'].values())<=components:raise ValueError('Creation role target absent')
    for mount in m['mounts']:
        if mount['component'] not in components or mount['world_object'] not in worlds:raise ValueError('Mount target absent')
    for e in m['concept_envelopes']:
        if e['world_object'] not in worlds:raise ValueError('Concept envelope absent')
    for e in m['dependencies']:
        if e['source'] not in worlds or e['target'] not in worlds:raise ValueError('Concept dependency absent')
    if m['state']=='EMPTY':
        if worlds or components or p['interfaces'] or m['controller_family']!='NONE':raise ValueError('Initial project must actually be empty')
    elif m['family']=='sensor_barrier':
        if set(m['world_roles'])!={'floor','support','pivot','beam','sensor','board_mount','target'} or set(m['component_roles'])!={'board','sensor','servo','supply','upper','lower'} or m['controller_family']!='TRUSTED_BARRIER_V1':raise ValueError('Incomplete barrier bindings')
    elif components or p['interfaces'] or m['controller_family']!='NONE':raise ValueError('Concept electronics/controller are unavailable')
    if m['state']=='BUILT' and m['empty_project_sha256'] is None:raise ValueError('Built project needs empty-state provenance')
    return m

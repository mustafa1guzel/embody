"""Bounded declarative robots and inspection-only XML. No assets or execution."""
import copy,re
from xml.etree import ElementTree as ET
from ide_api import rail_sweeps as rail,native_models as models
from ide_api.experiment_designer import text
from ide_api.research.artifacts import finite_json
FORMAT='EMBODY_ROBOT_PROJECT_V1'
MAX_BYTES=16384

def validate(value):
    # Reparse bounded strict JSON to reject duplicate/nonfinite/unsupported values.
    value=finite_json(value.encode() if isinstance(value,str) else value if isinstance(value,bytes) else rail.canonical(value),MAX_BYTES)
    rail.exact(value,['format','title','model_id','controller_id','parameters','requirements'])
    if value['format']!=FORMAT:raise ValueError('Unsupported declarative robot format')
    title=text(value['title'],80);module=models.for_model(value['model_id'])
    if value['controller_id']!=module.CONTROLLER:raise ValueError('Controller is not registered for this model')
    parameters=module.parameters(value['parameters']);requirements=module.criteria(value['requirements'])
    if value['model_id']==models.RAIL:
        d=module.DEFAULT_CRITERIA;c=requirements
        if c['minimumClearance']<d['minimumClearance'] or c['maximumFinalSpeed']>d['maximumFinalSpeed'] or c['maximumSettlingTime']>d['maximumSettlingTime'] or c['maximumContactEpisodes']>d['maximumContactEpisodes']:raise ValueError('Mandatory rail acceptance cannot be weakened')
    return {**copy.deepcopy(value),'title':title,'parameters':parameters,'requirements':requirements}

def template(model_id,title):
    d=models.descriptor(model_id)
    return validate({'format':FORMAT,'title':title,'model_id':model_id,'controller_id':d['controller_id'],'parameters':d['defaults'],'requirements':d['requirements']})

def inspect_xml(content):
    """Small read-only topology subset. Never resolve external assets or compile XML."""
    if not isinstance(content,str) or not 1<=len(content.encode())<=32768:raise ValueError('Inspection XML must be 1–32768 bytes')
    if re.search(r'<!|<\?|\b(?:file|filename|meshdir|texturedir|assetdir|href)\s*=',content,re.I):raise ValueError('Declarations/entities/processing instructions/external assets refused')
    try:root=ET.fromstring(content)
    except ET.ParseError:raise ValueError('Invalid bounded XML') from None
    nodes=list(root.iter())
    if len(nodes)>128:raise ValueError('XML structure limit')
    def depth(n,level=0):
        if level>12:raise ValueError('XML depth limit')
        for c in n:depth(c,level+1)
    depth(root)
    if root.tag not in ('robot','mujoco'):raise ValueError('Only URDF/MJCF structural inspection supported')
    allowed={'robot','link','joint','parent','child','axis','origin','limit','visual','collision','geometry','box','cylinder','sphere','inertial','mass','inertia'} if root.tag=='robot' else {'mujoco','worldbody','body','joint','freejoint','geom','inertial','option','actuator','motor'}
    unsupported=sorted({n.tag for n in nodes if n.tag not in allowed})
    links=[];joints=[]
    for n in nodes:
        if n.tag in ('link','body'):
            name=n.get('name')
            if not name or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,47}',name):raise ValueError('Bounded explicit structural names required')
            if name in links:raise ValueError('Duplicate structural link')
            links.append(name)
        if n.tag=='joint':joints.append({'name':n.get('name'),'type':n.get('type'),'parent':n.find('parent').get('link') if n.find('parent') is not None else None,'child':n.find('child').get('link') if n.find('child') is not None else None})
    if root.tag=='robot':
        parents={}
        for j in joints:
            if j['parent'] not in links or j['child'] not in links or j['child'] in parents:raise ValueError('Missing/duplicate joint parentage')
            parents[j['child']]=j['parent']
        for child in parents:
            seen={child};p=parents[child]
            while p in parents:
                if p in seen:raise ValueError('Cyclic imported topology')
                seen.add(p);p=parents[p]
    return {'format':'URDF' if root.tag=='robot' else 'MJCF','status':'STRUCTURAL_INSPECTION_ONLY','links':links,'joints':joints,'unsupported_elements':unsupported,'executable':False,'registered_model':None,'assets_resolved':False,'geometry_metadata':[{'tag':n.tag,'attributes':dict(n.attrib)} for n in nodes if n.tag in ('box','cylinder','sphere','geom')],'limitations':['No imported XML is admitted to native execution. No mesh/assets/external references, expressions, full semantics or dynamic validation.']}

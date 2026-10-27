"""EngineeringChangeSet result contract shared by preview, review and apply."""
from jsonschema import Draft202012Validator
from world.schema import obj
from .actions import OPERATIONS,CLASSIFICATIONS
from .project import validate,identity

SHA={'type':'string','pattern':'^[0-9a-f]{64}$'}
STRINGS={'type':'array','items':{'type':'string'},'maxItems':32}
CHANGESET_SCHEMA=obj({'schema_version':{'const':1},'base_project_sha256':SHA,'base_revision':{'type':'integer','minimum':0,'maximum':999999},'operations':OPERATIONS,'dependency_order':{'type':'array','items':{'type':'integer','minimum':0,'maximum':15},'minItems':1,'maxItems':16},'affected_subsystems':{'type':'array','items':{'enum':['world','circuit','device','interfaces','shapes']},'minItems':1,'maxItems':5},'preconditions':STRINGS,'validation':obj({'world':{'const':'VALID_COMPILED'},'world_contract_sha256':SHA,'electrical':{'type':'object','required':['status','errors','unknowns','diagnostics']},'interfaces':{'const':'VALID_TYPED_MAPPINGS'},'simulation':{'const':'NOT_RUN; no dynamic expected outcome inferred'}}),'expected_outcomes':STRINGS,'unknown_consequences':STRINGS,'approval_status':{'enum':['PROPOSED_NOT_APPLIED','INVALID_REVIEW_ONLY']},'proposed_project':{'type':'object','description':'Exact authoritative project schema; independently validated by engineering.project.validate.'},'resulting_project_sha256':SHA,'resulting_revision':{'type':'integer','minimum':1,'maximum':999999},'explanation':{'type':'string','minLength':1,'maxLength':2000},'origin':{'enum':['MODEL_TOOL_UNTRUSTED_PROPOSAL','EXPLICIT_LOCAL_USER_REVIEW','DEVELOPER_AUTHORED_EVIDENCE_PROPOSAL']},'model_application_authority':{'const':False},'installation_effect':{'const':'NONE'}})

CHANGESET_SCHEMA['properties']['validation']['properties']['shapes']={'type':'object','required':['parts','shape_spec_schema','source_sha256']}


def validate_changeset(v):
    if not Draft202012Validator(CHANGESET_SCHEMA).is_valid(v):raise ValueError('Invalid EngineeringChangeSet result schema')
    p=validate(v['proposed_project'])
    if identity(p)!=v['resulting_project_sha256'] or p['revision']!=v['resulting_revision'] or v['dependency_order']!=list(range(len(v['operations']))) or v['affected_subsystems']!=sorted({CLASSIFICATIONS[o['kind']]['subsystem'] for o in v['operations']}):raise ValueError('EngineeringChangeSet result identity/dependency mismatch')
    return v

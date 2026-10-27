"""Bounded review-only inspect -> propose -> explain -> model revision protocol.

No client or network here. Caller must separately authorize a live transport.
Every submitted full plan is supplied by the author; this class generates none.
"""
import copy
from jsonschema import Draft202012Validator
from physics.contracts import digest
from world.schema import obj
from .assembly_live import tools_for,observation,wire_schema
from .shape_live import compact_schema
from .assembly_plan import PLAN

def proposal_schema():
 """The same exact typed plan contract for offline and authorized live callers."""
 planning=copy.deepcopy(PLAN)
 for op in planning['properties']['steps']['items']['properties']['operations']['items']['anyOf']:
  kind=op['properties']['kind']['enum'][0]
  if kind=='create_object':op['properties']['primitive']['enum']=[p for p in op['properties']['primitive']['enum'] if p!='dynamic_body']
  if kind=='create_joint':op['properties']['joint']['anyOf'][0]['properties']['kind']['enum']=['revolute','prismatic']
 return [{'type':'function','name':'propose_assembly_plan','strict':True,'description':'Submit your own complete plan using create_free_root for the mobile root, never low-level free joint fields. revision_of must be null initially or the exact returned failure ID when revising. No automatic corrections. Validation is compilation only; physical checks need a separate trusted preview. At most two proposals, stop after success.','parameters':compact_schema(wire_schema(obj({'expected_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'expected_revision':{'type':'integer','enum':[0]},'revision_of':{'anyOf':[{'type':'null'},{'type':'string','pattern':'^[0-9a-f]{64}$'}]},'plan':planning})))}]

class AssemblyRevisionTools:
 def __init__(self,composer,trace,*,max_proposals=2):
  if type(max_proposals) is not int or not 1<=max_proposals<=2:raise ValueError('At most two author-supplied proposals')
  self.composer=composer;self.trace=trace;self.max_proposals=max_proposals;self.inspected=False;self.attempts=[];self.result=None;self.done=False;self.obs=observation(composer)
 @property
 def schemas(self):
  if self.done:return []
  if not self.inspected:return tools_for(0)
  return proposal_schema()
 def dispatch(self,name,args):
  try:
   schema=next((s for s in self.schemas if s['name']==name),None)
   if schema is None:raise ValueError('Protocol complete or tool unavailable')
   Draft202012Validator(schema['parameters']).validate(args)
   if observation(self.composer)!=self.obs:raise ValueError('Frozen authoritative inspection changed')
   if not self.inspected:self.inspected=True;out={'ok':True,'result':copy.deepcopy(self.obs)}
   else:
    if args['revision_of']!=(self.attempts[-1]['failure_id'] if self.attempts else None):raise ValueError('Revision must reference exact preceding rejected attempt')
    if len(self.attempts)>=self.max_proposals:raise ValueError('Proposal budget exhausted')
    assessment=self.composer.assess(args['expected_sha256'],args['expected_revision'],args['plan'])
    if assessment['status']=='COMPILED_REVIEW_READY':
     q=self.composer.propose(args['expected_sha256'],args['expected_revision'],args['plan'],origin='AUTHOR_SUPPLIED_REVISION_PROTOCOL')
     out={'ok':True,'result':q,'assessment':assessment,'revision_of':args['revision_of']};self.done=True
    else:
     failure={'plan':copy.deepcopy(args['plan']),'assessment':assessment,'revision_of':args['revision_of'],'author':'Supplied by caller; actual provider trace required before calling this live AI.'}
     key=self.composer.failures.put({'status':'REJECTED_NO_HEAD_CHANGE','base_project_sha256':args['expected_sha256'],'base_revision':args['expected_revision'],'plan':failure['plan'],'error':{'type':'AssemblyAssessment','message':'Whole-plan validation rejected','diagnostics':assessment['diagnostics']},'origin':'AUTHOR_SUPPLIED_REVISION_PROTOCOL','revision_of':args['revision_of']})
     out={'ok':False,'failure_id':key,'assessment':assessment,'revision_of':args['revision_of']};self.attempts.append({'failure_id':key,'plan_sha256':digest(args['plan'])})
     if len(self.attempts)>=self.max_proposals:self.done=True
    self.result=out
  except Exception as exc:self.done=True;out={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)[:400]}}
  self.trace.append('assembly_revision_tool_completed',{'name':name,'output':out,'new_model_requests':0});return out

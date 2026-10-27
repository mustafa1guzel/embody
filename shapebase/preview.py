"""Bounded trusted native collision-proxy preview, never construction application."""
from uuid import uuid4
import os
from engineering.changes import validate_changeset
from engineering.project import identity
from engineering.store import Store
from world.simulation import run
from physics.contracts import digest
from robustness.contracts import write_once
from .geometry import library

def run_preview(service,sha,revision,proposal_id):
 with service.transaction():
  before=service._precondition(sha,revision);proposal=validate_changeset(service.proposals.get(proposal_id))
  if proposal['base_project_sha256']!=sha or proposal['base_revision']!=revision:raise ValueError('Stale SHAPEBASE proposal')
  candidate,checks=service.preview(before,proposal['operations'])
  if not candidate.get('shape_specs') or digest(candidate)!=proposal['resulting_project_sha256'] or checks.get('shapes')!=proposal['validation'].get('shapes'):raise ValueError('Shape review/proxy/source identity mismatch')
  folder=service.root/'shape_previews';Store(folder)
  for index in (0,1):
   try:
    fd=os.open(folder/(proposal_id+'_'+str(index)+'.reservation'),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    os.close(fd);break
   except FileExistsError:continue
  else:raise ValueError('Two native proxy previews already reserved for this exact proposal')
 output=folder/('run_'+uuid4().hex);result=run(candidate['world'],output)
 assert result['independent_verification']['status']=='PASS'
 report={'status':'NATIVE_PROXY_REPLAY_PASS','physical_claim':'Only the declared collision/mass proxy; no through-hole contact, CAD solid, material or hardware verification','proposal_id':proposal_id,'base_project_sha256':sha,'proposed_project_sha256':identity(candidate),'shape_specs_sha256':digest(candidate['shape_specs']),'shape_source_sha256':library(candidate)['source_sha256'],'result':result,'evidence_path':str(output),'head_sha256_after':identity(service.current()),'application_status':'PROPOSED_NOT_APPLIED','new_model_requests':0,'vm_launches':0}
 write_once(output/'shape_verification.json',report)
 return report

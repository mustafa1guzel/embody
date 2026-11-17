"""Trusted operator preparation/approval registration; never fabricates consent.

A hash or a hand-manufactured record is not current-user authorization. Register
only after actual fresh explicit user approval of the exact reviewed manifest.
No paid call is dispatched by this CLI. Browser start uses the existing Server.job
only after the separately registered approval passes every gate again.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ide_api.agent_live_history import recover
from ide_api.engineering_agent_live import EngineeringAgentLive
from ide_api.engineering_agent import EngineeringAgent
from ide_api.product_alpha import ProductAlpha
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.rail_sweeps import RailSweeps,write_once
from ide_api.toolkit import Toolkit
from workspace.data import bounded_read,decode_json

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['admit-history','prepare','check','register-approval']);p.add_argument('--history-root',type=Path);p.add_argument('--context-file',type=Path);p.add_argument('--task');p.add_argument('--mode',choices=['inspect','analyze','propose'],default='inspect');p.add_argument('--request');p.add_argument('--approval-file',type=Path);a=p.parse_args()
 agent=EngineeringAgent(ProductAlpha(ExperimentDesigner(RailSweeps())),Toolkit());service=EngineeringAgentLive(agent)
 if a.action=='admit-history':
  if a.history_root is None:p.error('Explicit original accounting root required')
  value=recover(a.history_root);write_once(service.root/'history_admission.json',value,80000);(service.root/'history_admission.json').chmod(0o600);print(json.dumps({'status':'ADMITTED_EXISTING_HISTORY_NOT_SPENDING_APPROVAL','leaf_count':value['leaf_count'],'accounted_usd':value['accounted_cost_usd']}));return
 if a.action=='prepare':
  if a.context_file is None or a.task is None:p.error('Exact context-file and task required')
  c=decode_json(bounded_read(a.context_file.parent,a.context_file.name));v=service.prepare(c,agent.context(c)['context_sha256'],a.task,a.mode)
 elif a.action=='check':v={'status':'PREFLIGHT_PASS_NOT_APPROVED','context_sha256':service.preflight(a.request)['context_sha256']}
 else:
  if a.approval_file is None:p.error('Actual separately recorded explicit approval required')
  v=service.register_approval(a.request,decode_json(bounded_read(a.approval_file.parent,a.approval_file.name)))
 print(json.dumps(v,indent=2))
if __name__=='__main__':main()

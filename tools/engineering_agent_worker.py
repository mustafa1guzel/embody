"""Fixed trusted numerical-agent worker. No commands, modules, roots or SDK bypass arguments."""
import argparse
from core.simulation import ROOT
from ide_api.engineering_agent import EngineeringAgent
from ide_api.engineering_agent_live import EngineeringAgentLive
from ide_api.product_alpha import ProductAlpha
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.rail_sweeps import RailSweeps
from ide_api.toolkit import Toolkit

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',required=True);a=p.parse_args()
 agent=EngineeringAgent(ProductAlpha(ExperimentDesigner(RailSweeps())),Toolkit());live=EngineeringAgentLive(agent)
 folder=live._folder(a.request)
 if not (folder/'worker_begin.json').is_file():raise SystemExit('BLOCKED: no server-owned worker reservation')
 approval=live.approval(a.request);live.execute(a.request,approval)
if __name__=='__main__':main()

"""Operator entry point for a separately approved workspace request.

Preparation grants no execution authority. No browser approval route exists.
An explicit current-user approval record of the displayed exact manifest is
required; constructing a record or supplying its hash is not user consent.
"""
import argparse
from pathlib import Path
import sys
import signal

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ide_api.engineering_ai import EngineeringAI
from workspace.data import bounded_read,decode_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',required=True)
    p.add_argument('--approval',type=Path,help='Separately recorded explicit current-user approval, never a CLI hash alone')
    p.add_argument('--verify',action='store_true',help='Explicitly spend the single approved native preview after compilation')
    a=p.parse_args()
    if a.approval is None:raise SystemExit('BLOCKED: no separate explicit approval; no credentials, client or physics created')
    approval=decode_json(bounded_read(a.approval.parent,a.approval.name))
    service=EngineeringAI(ROOT/'artifacts/phase19c/workspace_requests')
    # No transport injection/alternate endpoint/model or bypass switch in this CLI.
    def expired(*unused):raise TimeoutError('Approved execution window exhausted; no retry')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,600)
    try:value=service.verify(a.request,approval) if a.verify else service.execute(a.request,approval)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    print(value['status'])

if __name__=='__main__':main()

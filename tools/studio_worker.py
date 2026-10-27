"""Fixed trusted entry point; native operator receipt required, no model source."""
import argparse
import signal
import time
from pathlib import Path

from ide_api.engineering_ai import EngineeringAI
from engineering.store import Store
from physics.contracts import digest
from robustness.contracts import write_once


def execute(ai,key,receipt,folder,*,offline_client=None):
    events=folder/'events';events.mkdir(exist_ok=True);sequence=0
    def event(name,payload):
        nonlocal sequence
        write_once(events/f'{sequence:03d}.json',{'event':name,'payload':payload,'recorded_unix':time.time()});sequence+=1
    value=ai.execute(key,receipt['approval'],offline_client=offline_client,on_event=event)
    if value['status']=='COMPILED' and receipt['native_preview']:
        value=ai.verify(key,receipt['approval'],on_event=event)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--request',required=True);p.add_argument('--review',required=True);a=p.parse_args()
    ai=EngineeringAI(a.root);ai.requests.get(a.request);folder=ai.root/'studio_runs'/a.request
    from workspace.data import bounded_read,decode_json
    receipt=decode_json(bounded_read(folder,'operator_receipt.json'));q=Store(ai.root/'studio_quotes').get(a.review)
    if receipt['method']!='NATIVE_MACOS_OPERATOR_CONFIRMATION' or receipt['browser_approval_accepted'] is not False or receipt['review_id']!=a.review or receipt['quote_sha256']!=digest(q) or q['request_id']!=a.request or receipt['native_preview']!=bool(q['policy']['native_previews']):raise ValueError('Exact native operator receipt required')
    if not time.time()<q['expires_unix'] or not 0<=time.time()-receipt['approval']['approved_unix']<=120:raise ValueError('Native approval handoff expired; no replay')
    ai.gate(a.request,receipt['approval'])
    write_once(folder/'worker_claimed.json',{'request_id':a.request,'claimed_unix':time.time(),'replay_permitted':False})
    def expired(*_):raise TimeoutError('Authorized worker execution window exhausted')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,q['policy']['window_seconds'])
    try:execute(ai,a.request,receipt,folder)
    finally:signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':main()

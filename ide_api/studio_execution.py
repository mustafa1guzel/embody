"""Studio initiation, native operator consent, and a fixed deadline-bound worker.

No HTTP-supplied approval, command, client, model, path or transport is accepted.
Same-origin writes are necessary but are not financial authorization.
"""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time

from core.simulation import ROOT
from engineering.store import Store
from physics.contracts import digest
from robustness.contracts import write_once
from workspace.data import bounded_read, decode_json

SCRIPT = '''on run argv
set answer to display dialog (item 1 of argv) with title "EMBODY — authorize engineering" buttons {"Cancel", "Start building"} default button "Cancel" cancel button "Cancel" giving up after 120
if gave up of answer then return "DENIED"
if button returned of answer is "Start building" then return "EXPLICIT_APPROVE"
return "DENIED"
end run'''


class NativeOperator:
    def available(self):
        p=Path('/usr/bin/osascript')
        return platform.system()=='Darwin' and p.is_file() and not p.is_symlink() and p.stat().st_uid==0 and not p.stat().st_mode&0o022

    def confirm(self,quote):
        if not self.available():raise PermissionError('Native Mac confirmation unavailable. Use the existing separately approved local operator workflow.')
        # Fixed system executable/source; task is data in argv, never executable text.
        text=(f"Authorize this exact engineering request?\n\n{quote['task']}\n\n"
              f"GPT-5.4 low · at most {quote['policy']['max_requests']} requests\n"
              f"Hard spending cap: ${quote['policy']['hard_cap_usd']} USD\n"
              f"Conservative reservation: ${quote['policy']['maximum_reservation_usd']}\n"
              f"Native physics: {'ONE 200-step preview + fresh 200-step replay' if quote['policy']['native_previews'] else 'NOT permitted'}\n"
              f"Review only; no project application, VM or controller execution.\n"
              f"Project: {quote['project_sha256']}\nExact scope: {quote['manifest_sha256']}\n"
              "Cancel is the default. Confirm only your own intended request.")
        result=subprocess.run(['/usr/bin/osascript','-e',SCRIPT,'--',text],capture_output=True,text=True,timeout=125,check=False)
        return result.returncode==0 and result.stdout.strip()=='EXPLICIT_APPROVE'


class StudioExecution:
    def __init__(self,ai,*,operator=None,runner=None):
        self.ai=ai;self.quotes=Store(ai.root/'studio_quotes')
        self.operator=operator or NativeOperator();self.runner=runner
        self.guard=threading.Lock();self.jobs={};self.live={}

    def _folder(self,key):
        self.ai.requests.get(key)  # Exact immutable ID, never an arbitrary path.
        folder=self.ai.root/'studio_runs'/key
        if any(p.is_symlink() for p in (folder,*folder.parents)):raise ValueError('Symlink studio run rejected')
        return folder

    def quote(self,key):
        d=self.ai.preflight(key)
        if (self._folder(key)/'begin.json').exists():raise ValueError('Studio initiation already consumed. Read its outcome; no retry.')
        if len(list(self.quotes.root.glob('*.json')))>=256:raise ValueError('Local run-review limit reached; preserve old records')
        q={'request_id':key,'manifest_sha256':self.ai.requests.get(key)['sha256'],'task':d['task'],
           'project_sha256':d['project_sha256'],'project_revision':d['project_revision'],'policy':d['policy'],
           'expires_unix':min(time.time()+120,d['frozen_unix']+d['policy']['freeze_validity_seconds']),
           'authorization':'NATIVE_LOCAL_OPERATOR_CONFIRMATION_REQUIRED_NOT_BROWSER_CONSENT'}
        key=self.quotes.put(q)
        return {**q,'review_id':key,'native_confirmation_supported':self.operator.available(),
                'meaning':'Review is free. Start building opens native operator confirmation; no approval is accepted from the web page.'}

    def _quote(self,review_id):
        q=self.quotes.get(review_id)
        if not time.time()<q['expires_unix']:raise ValueError('Run review expired. No execution started; review the request again.')
        d=self.ai.preflight(q['request_id'])
        if self.ai.requests.get(q['request_id'])['sha256']!=q['manifest_sha256'] or d['project_sha256']!=q['project_sha256'] or d['policy']!=q['policy']:raise ValueError('Reviewed request identity changed')
        return q

    def launch(self,review_id,job):
        with self.guard:
            # Exact duplicate returns the same server job, never a second dispatch.
            if review_id in self.jobs:return self.jobs[review_id]
            q=self._quote(review_id)
            if (self._folder(q['request_id'])/'begin.json').exists():raise ValueError('Studio initiation consumed or interrupted. Check the saved outcome.')
            value=job(lambda:self.run(review_id));self.jobs[review_id]=value
            return value

    def run(self,review_id):
        q=self._quote(review_id);key=q['request_id'];folder=self._folder(key);folder.mkdir(parents=True,exist_ok=True)
        write_once(folder/'begin.json',{'review_id':review_id,'request_id':key,'started_unix':time.time(),'authorization':'NOT_YET_GRANTED'})
        self.live[key]={'stage':'awaiting_native_confirmation','started':time.time()}
        try:
            if not self.operator.confirm(q):
                write_once(folder/'finished.json',{'status':'OPERATOR_DECLINED','model_started':False})
                return {'status':'OPERATOR_DECLINED','message':'Native confirmation declined or unavailable. No model execution started. Cancel this request before preparing another.'}
            q=self._quote(review_id)  # Recheck after the human decision, before any client.
            approval={'request_id':key,'manifest_sha256':q['manifest_sha256'],'approved_unix':time.time(),
                      'decision':'EXPLICIT_APPROVE','authority':'CURRENT_USER_EXPLICIT_APPROVAL'}
            receipt={'review_id':review_id,'quote_sha256':digest(q),'approval':approval,'native_preview':bool(q['policy']['native_previews']),
                     'method':('NATIVE_MACOS_OPERATOR_CONFIRMATION' if isinstance(self.operator,NativeOperator) and self.runner is None else 'OFFLINE_OPERATOR_FIXTURE_NOT_USER'),'browser_approval_accepted':False}
            write_once(folder/'operator_receipt.json',receipt)
            self.live[key]={'stage':'authorized_worker_starting','started':time.time()}
            if self.runner is not None:
                # Explicit Python-only dependency injection for labelled tests/QA.
                value=self.runner(self.ai,key,receipt,folder)
            else:
                command=[sys.executable,'-m','tools.studio_worker','--root',str(self.ai.root.resolve()),'--request',key,'--review',review_id]
                with subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as process:
                    self.live[key]['process']=process
                    try:code=process.wait(timeout=q['policy']['window_seconds'])
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait();raise TimeoutError('Worker deadline exhausted; execution/cost may be unknown. Never retry this scope.') from None
                value=self.ai.read(key)
                if code and value['status'] not in ('FAILED','CONSTRUCTION_REJECTED','PHYSICAL_FAIL'):raise RuntimeError('Worker stopped without a confirmed outcome; check saved records')
            write_once(folder/'finished.json',{'status':value['status']})
            return {'status':value['status'],'request_id':key}
        except Exception as exc:
            if not (folder/'finished.json').exists():write_once(folder/'finished.json',{'status':'STOPPED_OR_UNKNOWN','type':type(exc).__name__,'message':str(exc)[:400]})
            raise
        finally:self.live.pop(key,None)

    def status(self,key):
        folder=self._folder(key);state=self.live.get(key);events=[]
        for p in sorted((folder/'events').glob('*.json')):
            events.append(decode_json(bounded_read(p.parent,p.name)))
        finished=decode_json(bounded_read(folder,'finished.json')) if (folder/'finished.json').exists() else None
        active=state is not None
        if active and 'process' in state:active=state['process'].poll() is None
        stage=(events[-1]['event'] if events else state['stage']) if active else finished['status'] if finished else 'UNKNOWN_OUTCOME' if (folder/'begin.json').exists() else 'NOT_STARTED'
        return {'request_id':key,'active':active,'stage':stage,'events':events[-24:],'finished':finished,
                'checked_unix':time.time(),'native_confirmation_supported':self.operator.available(),
                'meaning':'Active requires this server-owned live job/process. A reservation alone never proves running.'}

"""Small same-origin loopback HTTP API; no shell, arbitrary path or exec endpoint.

Uses the standard library to avoid changing the verified Python environment.
Only one expensive/mutating job is admitted. Requests are bounded, exact-schema
JSON. Browser writes require an allowed Origin and process-scoped CSRF token.
"""
from __future__ import annotations
import argparse
import hmac
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

from core.agent.patching import READ_ALLOWLIST
from core.agent.credentials import read_openai_api_key, CredentialsMissing, CredentialConfigurationError
from core.agent.vm_backend import AppleVMBackend
from core.simulation import ROOT
from workspace.data import bounded_read, decode_json
from workspace.workflow import WorkflowBlocked
from ide_api.service import IDE
from ide_api.agent import CONSENT, run_live

MAX_BODY=160_000


def exact(body,fields):
    if not isinstance(body,dict) or set(body)!=set(fields):
        raise ValueError('Request fields must match the declared schema')


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address=('127.0.0.1',8765),*,ide=None):
        if address[0]!='127.0.0.1':raise ValueError('Only loopback binding is permitted')
        super().__init__(address,Handler)
        self.ide=ide or IDE();self.token=secrets.token_urlsafe(32)
        self.job_lock=threading.Lock();self.jobs={};self.jobs_guard=threading.Lock()
        self.host=f'127.0.0.1:{self.server_port}'
        self.origins={f'http://{self.host}','http://127.0.0.1:5173'}

    def job(self,operation):
        if not self.job_lock.acquire(blocking=False):
            raise WorkflowBlocked('A verification, transaction or live agent is already running')
        job_id=uuid4().hex
        with self.jobs_guard:self.jobs[job_id]={'id':job_id,'status':'RUNNING'}
        def work():
            try:
                value=operation()
                result={'id':job_id,'status':'COMPLETED','result':value}
            except (ValueError,OSError,RuntimeError) as exc:
                # Model transport failures have their own sanitized evidence.
                result={'id':job_id,'status':'BLOCKED','error':str(exc)[:512]}
            except Exception:
                result={'id':job_id,'status':'BLOCKED','error':'Operation failed; inspect local sanitized evidence'}
            finally:self.job_lock.release()
            with self.jobs_guard:self.jobs[job_id]=result
        threading.Thread(target=work,daemon=True).start()
        return {'job_id':job_id}


class Handler(BaseHTTPRequestHandler):
    server:Server
    def log_message(self,*_):pass # no prompts, query strings, credentials or headers in access logs

    def reply(self,status,value,content_type='application/json'):
        raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode() if content_type=='application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        # Local Monaco workers need blob workers; no remote scripts/fonts/CDNs.
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        origin=self.headers.get('Origin')
        if origin in self.server.origins:
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
        self.end_headers();self.wfile.write(raw)

    def guard(self,write=False):
        if self.headers.get('Host')!=self.server.host:
            raise PermissionError('Loopback Host required')
        origin=self.headers.get('Origin')
        if origin is not None and origin not in self.server.origins:
            raise PermissionError('Origin is not allowed')
        if self.headers.get('Sec-Fetch-Site')=='cross-site':raise PermissionError('Cross-site request rejected')
        if write and (origin not in self.server.origins or not hmac.compare_digest(self.headers.get('X-EMBODY-Token',''),self.server.token)):
            raise PermissionError('Explicit same-origin write token required')

    def do_GET(self):
        try:
            self.guard()
            route=urlsplit(self.path);q=parse_qs(route.query,strict_parsing=True)
            def one(name):
                if set(q)!={name} or len(q[name])!=1:raise ValueError('Invalid query fields')
                return q[name][0]
            path=route.path;ide=self.server.ide
            if path=='/api/health':
                if q:raise ValueError('Unexpected query')
                from ide_api.startup import check
                return self.reply(200,check())
            if path=='/api/workspace':
                from ide_api.workspace import bootstrap
                key=one('project')
                if key=='ai-review':
                    from types import SimpleNamespace
                    value=bootstrap(SimpleNamespace(engineering=ide.engineering_ai.draft()))
                    value['snapshot'].update(key='ai-review',title='AI review project · EMPTY r0',editable=False,
                        context='Independent current-source review project. No proposal is applied by AI or verification.')
                else:value=bootstrap(ide,key)
                value['projects'].append({'key':'ai-review','title':'AI review project · open after creation'})
                return self.reply(200,value)
            if path=='/api/ai-engineering/execution-status':return self.reply(200,ide.studio_execution.status(one('id')))
            if path=='/api/ai-engineering/followup':return self.reply(200,ide.engineering_ai.read_followup(one('id')))
            if path=='/api/ramp-review':return self.reply(200,ide.ramp.read(one('id')))
            if path=='/api/ai-engineering/request':
                return self.reply(200,ide.engineering_ai.read(one('id')))
            if path=='/api/ai-engineering/context':
                if q:raise ValueError('Unexpected query')
                from engineering.assembly import AssemblyComposer
                from engineering.assembly_live import observation
                return self.reply(200,observation(AssemblyComposer(ide.engineering_ai.draft())))
            if path=='/api/construction-review/bootstrap':
                if q:raise ValueError('Unexpected query')
                return self.reply(200,ide.construction_review.bootstrap())
            if path=='/api/construction-review/measurement':return self.reply(200,{'measurement':ide.construction_review.latest(one('review_id'))})
            if path=='/api/creation/capabilities':
                if q:raise ValueError('Unexpected query')
                return self.reply(200,{'capabilities':ide.creation.capabilities(),'projects':ide.creation.list_projects()})
            if path=='/api/engineering/shape_agent_review':
                if q:raise ValueError('Unexpected query')
                from engineering.shape_agent_review import load_review
                return self.reply(200,load_review(ide.engineering))
            if path=='/api/engineering/assembly/bootstrap':
                if q:raise ValueError('Unexpected query')
                from engineering.assembly import AssemblyComposer
                return self.reply(200,AssemblyComposer(ide.engineering).bootstrap())
            if path=='/api/engineering/evidence':return self.reply(200,ide.engineering.load_evidence(one('key')))
            if path in ('/api/engineering/bootstrap','/api/engineering/context'):
                if q:raise ValueError('Unexpected query')
                return self.reply(200,ide.engineering.bootstrap() if path.endswith('bootstrap') else ide.engineering.inspect_context())
            if path=='/api/hardware/bootstrap':
                if q:raise ValueError('Unexpected query')
                return self.reply(200,ide.hardware.bootstrap())
            if path=='/api/hardware/load':return self.reply(200,ide.hardware.load(one('key')))
            if path=='/api/robustness':
                if q:raise ValueError('Unexpected query')
                return self.reply(200,ide.robustness())
            arm=path.startswith('/api/arm/')
            if arm:
                path=path.replace('/api/arm/','/api/',1)
                if path=='/api/recording':
                    if q:raise ValueError('Unexpected query')
                    return self.reply(200,ide.arm_recording().metadata())
                if path=='/api/experiment':return self.reply(200,ide.arm_recording().experiment(one('scenario')))
                if path=='/api/file':return self.reply(200,ide.arm_file(one('path')))
                if path=='/api/proposal':return self.reply(200,ide.arm_recording().proposal(one('variant')))
                if path not in ('/api/review','/api/review/source'):raise ValueError('Unknown arm read endpoint')
            workflow=ide.arm_workflow if arm else ide.workflow
            if path=='/api/bootstrap':
                if q:raise ValueError('Unexpected query')
                return self.reply(200,{'csrf_token':self.server.token,'files':ide.files(),
                    'recording_sha256':ide.recording.inventory_sha256,'api_cost_on_open':'0.00',
                    'live_policy':{'model':'gpt-5.4','reasoning':'low','session_cap_usd':'.50','project_cap_usd':'30','consent':CONSENT}})
            if path=='/api/file':return self.reply(200,ide.file(one('path')))
            if path=='/api/experiment':return self.reply(200,ide.experiment(one('scenario')))
            if path=='/api/physics':
                if set(q)!={'scenario','variant'} or any(len(v)!=1 for v in q.values()):
                    raise ValueError('Expected exactly scenario and variant')
                return self.reply(200,ide.physics(q['scenario'][0],q['variant'][0]))
            if path=='/api/proposal':return self.reply(200,ide.recording.proposal(one('variant')))
            if path=='/api/agent/recorded':
                if q:raise ValueError('Unexpected query')
                return self.reply(200,ide.recorded_agent())
            if path=='/api/review':return self.reply(200,workflow.get(one('id')))
            if path=='/api/review/source':
                identifier=one('id');state=workflow.get(identifier)
                folder=workflow._folder(identifier)
                source=bounded_read(folder,'proposed_source.txt').decode()
                original=bounded_read(folder,'original_source.txt').decode()
                return self.reply(200,{'original':original,'modified':source,'sha256':state['source_sha256']})
            if path=='/api/job':
                identifier=one('id')
                with self.server.jobs_guard:
                    if identifier not in self.server.jobs:raise ValueError('Unknown job ID')
                    return self.reply(200,self.server.jobs[identifier])
            if path.startswith('/api/'):return self.reply(404,{'status':'BLOCKED','error':'Unknown endpoint'})
            if q:raise ValueError('Unexpected static query')
            relative='index.html' if path=='/' else path.removeprefix('/')
            raw=bounded_read(ROOT/'frontend/dist',relative)
            return self.reply(200,raw,mimetypes.guess_type(relative)[0] or 'application/octet-stream')
        except PermissionError as exc:self.reply(403,{'status':'BLOCKED','error':str(exc)})
        except (ValueError,OSError,KeyError,TypeError) as exc:self.reply(400,{'status':'BLOCKED','error':str(exc)[:512]})
        except Exception:self.reply(500,{'status':'BLOCKED','error':'Read failed; no fallback evidence was substituted'})

    def do_POST(self):
        try:
            self.guard(write=True)
            if self.headers.get('Transfer-Encoding'):raise ValueError('Chunked input is not supported')
            if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON content type required')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY:raise ValueError('Request body exceeds limit or is empty')
            self.connection.settimeout(10)
            body=decode_json(self.rfile.read(length))
            route=urlsplit(self.path)
            if route.query:raise ValueError('Unexpected query fields')
            path=route.path;ide=self.server.ide
            if path=='/api/ramp-review':
                exact(body,['parameters']);return self.reply(200,ide.ramp.create(body['parameters']))
            if path=='/api/ramp-test':
                exact(body,['id']);return self.reply(200,self.server.job(lambda:ide.ramp.run(body['id'])))
            if path.startswith('/api/ai-engineering/'):
                action=path.removeprefix('/api/ai-engineering/');service=ide.engineering_ai
                if action=='new-project':
                    exact(body,[]);p=service.draft(create=True).current()
                    from engineering.project import identity
                    value={'project_key':'ai-review','project_sha256':identity(p),'revision':p['revision']}
                elif action=='prepare':
                    exact(body,['workflow','task','expected_sha256','expected_revision','selection','baseline_request_id']+(['run_options'] if isinstance(body,dict) and 'run_options' in body else []))
                    value=service.prepare(**body)
                elif action=='review-run':
                    exact(body,['request_id']);value=ide.studio_execution.quote(body['request_id'])
                elif action=='start-building':
                    exact(body,['review_id']);value=ide.studio_execution.launch(body['review_id'],self.server.job)
                elif action=='followup-wheels':
                    exact(body,['request_id','proposal_id','diameter_m']);value=service.followup(**body)
                elif action=='cancel':
                    exact(body,['request_id']);value=service.cancel(body['request_id'])
                elif action=='disposition':
                    exact(body,['request_id','decision']);value=service.disposition(body['request_id'],body['decision'])
                else:raise PermissionError('Browser cannot approve or execute paid/native requests or apply proposals. Prepare an exact scope for separate human approval.')
                return self.reply(200,value)
            if path.startswith('/api/construction-review/'):
                action=path.removeprefix('/api/construction-review/');service=ide.construction_review
                if action=='prepare':
                    exact(body,['expected_sha256','expected_revision']);value=service.prepare(body['expected_sha256'],body['expected_revision'])
                elif action=='preview':
                    exact(body,['review_id','expected_sha256','expected_revision'])
                    return self.reply(202,self.server.job(lambda:service.preview(body['review_id'],body['expected_sha256'],body['expected_revision'])))
                elif action=='commit':
                    exact(body,['review_id','expected_sha256','expected_revision','confirmation'])
                    value=service.commit(body['review_id'],body['expected_sha256'],body['expected_revision'],body['confirmation'])
                else:raise ValueError('Unknown construction review action')
                return self.reply(200,value)
            if path.startswith('/api/creation/'):
                action=path.removeprefix('/api/creation/')
                if action=='plan':exact(body,['request','parameters']);value=ide.creation.start(body['request'],body['parameters'])
                elif action=='decide':exact(body,['proposal_id','expected_sha256','expected_revision','decision','confirmation']);value=ide.creation.decide(body['proposal_id'],body['expected_sha256'],body['expected_revision'],body['decision'],body['confirmation'])
                elif action=='open':
                    exact(body,['project_id','confirmation'])
                    if body['project_id']=='engineering_project':
                        if body['confirmation']!='OPEN SUPPORTED PROJECT':raise ValueError('Explicit project selection required')
                        with ide.creation.transaction():ide.creation._activate('engineering_project',checked=True)
                        value=ide.engineering.bootstrap()
                    else:value=ide.creation.open(body['project_id'],body['confirmation'])
                else:raise ValueError('Unknown creation action')
                return self.reply(200,value)
            if path.startswith('/api/engineering/'):
                action=path.removeprefix('/api/engineering/');service=ide.engineering
                if action.startswith('assembly/'):
                    from engineering.assembly import AssemblyComposer
                    composer=AssemblyComposer(service);sub=action.removeprefix('assembly/')
                    if sub=='propose':
                        exact(body,['expected_sha256','expected_revision','plan']);value=composer.propose(body['expected_sha256'],body['expected_revision'],body['plan'])
                    elif sub=='assess':
                        exact(body,['expected_sha256','expected_revision','plan']);value=composer.assess(body['expected_sha256'],body['expected_revision'],body['plan'])
                    elif sub=='native':
                        exact(body,['expected_sha256','expected_revision','proposal_id'])
                        return self.reply(202,self.server.job(lambda:composer.preview_native(body['expected_sha256'],body['expected_revision'],body['proposal_id'])))
                    elif sub=='decide':
                        exact(body,['expected_sha256','expected_revision','proposal_id','decision','confirmation']);value=composer.decide(body['expected_sha256'],body['expected_revision'],body['proposal_id'],body['decision'],body['confirmation'])
                    else:raise ValueError('Unknown bounded assembly action')
                    return self.reply(200,value)
                if action in ('edit','propose'):
                    exact(body,['expected_sha256','expected_revision','operations']+(['explanation'] if action=='propose' else []))
                    value=service.propose(body['expected_sha256'],body['expected_revision'],body['operations'],body['explanation'],origin='EXPLICIT_LOCAL_USER_REVIEW') if action=='propose' else service.edit(body['expected_sha256'],body['expected_revision'],body['operations'])
                elif action=='circuit':
                    exact(body,['expected_sha256','expected_revision','assembly']);value=service.replace_circuit(body['expected_sha256'],body['expected_revision'],body['assembly'])
                elif action=='decide':
                    exact(body,['expected_sha256','expected_revision','proposal_id','decision','confirmation']);value=service.decide(body['expected_sha256'],body['expected_revision'],body['proposal_id'],body['decision'],body['confirmation'])
                elif action=='restore':
                    exact(body,['expected_sha256','expected_revision','key','confirmation'])
                    if body['confirmation']!='RESTORE PROJECT DATA':raise ValueError('Explicit revision restore required')
                    value=service.restore(body['expected_sha256'],body['expected_revision'],body['key'])
                elif action=='save':
                    exact(body,['expected_sha256','expected_revision']);value=service.save(body['expected_sha256'],body['expected_revision'])
                elif action=='plan':exact(body,['goal']);value=service.plan(body['goal'])
                elif action=='get_plan':exact(body,['plan_id']);value={'plan':service.plans.get(body['plan_id']),'plan_id':body['plan_id']}
                elif action=='review_plan':exact(body,['plan_id']);value=service.review_plan(body['plan_id'])
                elif action=='compile_plan':exact(body,['plan_id']);value=service.compile_plan(body['plan_id'])
                elif action=='shape_preview':
                    exact(body,['expected_sha256','expected_revision','proposal_id'])
                    return self.reply(202,self.server.job(lambda:service.preview_shapes(body['expected_sha256'],body['expected_revision'],body['proposal_id'])))
                elif action=='simulate':
                    exact(body,['expected_sha256','expected_revision','kind'])
                    return self.reply(202,self.server.job(lambda:service.simulate(body['expected_sha256'],body['expected_revision'],body['kind'])))
                else:raise ValueError('Unknown bounded engineering action')
                return self.reply(200,value)
            if path.startswith('/api/hardware/'):
                action=path.removeprefix('/api/hardware/');hardware=ide.hardware
                if action=='validate':exact(body,['assembly']);value=hardware.inspect(body['assembly'])
                elif action=='plan':exact(body,['request']);value=hardware.plan(body['request'])
                elif action=='edit':exact(body,['assembly','operation']);value=hardware.edit(body['assembly'],body['operation'])
                elif action=='save':exact(body,['assembly']);value=hardware.save(body['assembly'])
                elif action=='import':exact(body,['envelope']);value=hardware.import_data(body['envelope'])
                elif action=='propose':exact(body,['assembly','operations','explanation']);value=hardware.propose(body['assembly'],body['operations'],body['explanation'])
                elif action=='apply':exact(body,['assembly','proposal','confirmation']);value=hardware.apply(body['assembly'],body['proposal'],body['confirmation'])
                else:raise ValueError('Unknown hardware operation')
                return self.reply(200,value)
            if path=='/api/device/run':
                exact(body,['assembly','spec'])
                # Trusted reference logic only; no candidate source/executor argument.
                return self.reply(202,self.server.job(lambda:ide.hardware.run(body['assembly'],body['spec'])))
            arm=path.startswith('/api/arm/')
            if arm:
                path=path.replace('/api/arm/','/api/',1)
                if path not in ('/api/review/create','/api/review/action'):raise ValueError('Unknown arm mutation endpoint')
            workflow=ide.arm_workflow if arm else ide.workflow
            if path=='/api/prerequisites':
                exact(body,[]);result={}
                try:read_openai_api_key();result['credentials']='CONFIGURED — no request made'
                except (CredentialsMissing,CredentialConfigurationError):result['credentials']='BLOCKED — missing or invalid secure credentials'
                try:result['vm']=AppleVMBackend().preflight()
                except (ValueError,OSError,RuntimeError) as exc:result['vm']={'status':'BLOCKED','reason':str(exc)[:512]}
                return self.reply(200,result)
            if path=='/api/review/create':
                # Serialized with VM/model/transaction jobs. No implicit approvals.
                return self.reply(202,self.server.job(lambda:{'review_id':ide.review(body,family='arm' if arm else 'rail')}))
            if path=='/api/review/action':
                exact(body,['id','action','confirmation'])
                if any(not isinstance(v,str) for v in body.values()):raise ValueError('Action fields must be strings')
                identifier,action,confirmation=body['id'],body['action'],body['confirmation']
                workflow.get(identifier)
                if action=='verify':
                    if confirmation!='VERIFY IN VM ONLY':raise ValueError('Verification-only consent required')
                    operation=lambda:workflow.verify(identifier,approved=True)
                elif action=='reject':operation=lambda:(workflow.reject(identifier) or workflow.get(identifier))
                elif action=='apply':operation=lambda:(workflow.apply(identifier,confirmation=confirmation) or workflow.get(identifier))
                elif action=='rollback':operation=lambda:(workflow.rollback(identifier,confirmation=confirmation) or workflow.get(identifier))
                elif action=='results':operation=lambda:workflow.checked_verification(identifier)
                else:raise ValueError('Unknown review action')
                return self.reply(202,self.server.job(operation))
            if path=='/api/agent/start':
                exact(body,['mode','message','references','confirmation'])
                if body['confirmation']!=CONSENT:raise ValueError('Explicit paid-run confirmation required')
                if body['mode'] not in ('code','physical'):raise ValueError('Unknown agent workflow')
                if not isinstance(body['message'],str) or not 1<=len(body['message'].encode())<=8000:raise ValueError('Prompt size invalid')
                refs=body['references']
                if not isinstance(refs,list) or len(refs)>4 or any(not isinstance(p,str) or p not in READ_ALLOWLIST for p in refs):raise ValueError('Only four allowlisted references are permitted')
                # Credentials checked explicitly before accepting a paid job.
                read_openai_api_key()
                output=ROOT/'artifacts/day7/agent_sessions'/uuid4().hex
                return self.reply(202,self.server.job(lambda:run_live(output,body,ide.workflow)))
            return self.reply(404,{'status':'BLOCKED','error':'Unknown endpoint'})
        except PermissionError as exc:self.reply(403,{'status':'BLOCKED','error':str(exc)})
        except (CredentialsMissing,CredentialConfigurationError):self.reply(409,{'status':'BLOCKED','error':'Secure API credentials missing or invalid; no request made'})
        except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:self.reply(400,{'status':'BLOCKED','error':str(exc)[:512],'diagnostics':getattr(exc,'diagnostics',[])})
        except Exception:self.reply(500,{'status':'BLOCKED','error':'Operation rejected; no implicit retry'})


def main():
    parser=argparse.ArgumentParser(description='Serve the local production EMBODY app; never installs or runs models/physics on startup.')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--check',action='store_true',help='Validate installed dependencies and production assets, then exit without binding a port')
    args=parser.parse_args()
    try:
        if not 1<=args.port<=65535:raise ValueError('Choose a port from 1 to 65535')
        from ide_api.startup import check
        ready=check()
        if args.check:print(json.dumps(ready,indent=2));return
        server=Server(('127.0.0.1',args.port))
    except (ValueError,OSError) as exc:
        parser.exit(2,'Cannot start EMBODY: '+str(exc)+'\nIf the address is in use, stop your other server or choose --port <unused-port>. No process was stopped.\n')
    import signal
    def stop(*unused):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    print(f'EMBODY IDE: http://127.0.0.1:{server.server_port} (local only; no API requests on startup)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()

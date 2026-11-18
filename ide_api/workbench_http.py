"""Same-origin bounded local workbench extension; no provider or arbitrary executor."""
import argparse,json,signal
from urllib.parse import urlsplit,parse_qs
from ide_api.engineering_agent_http import EngineeringServer,EngineeringHandler
from ide_api.server import exact
from ide_api.workbench import Workbench
from workspace.data import decode_json
from jsonschema import ValidationError

class WorkbenchHandler(EngineeringHandler):
 def service(self):
  with self.server.jobs_guard:
   if not hasattr(self.server,'workbench'):self.server.workbench=Workbench()
   return self.server.workbench
 def do_GET(self):
  route=urlsplit(self.path)
  if not route.path.startswith('/api/workbench/'):return super().do_GET()
  try:
   self.guard();s=self.service();name=route.path.removeprefix('/api/workbench/');q=parse_qs(route.query,keep_blank_values=True)
   required={'bootstrap':[],'project':['id'],'run':['id','nonce'],'report':['id','nonce'],'controller-run':['id','nonce'],'controller-report':['id','nonce'],'controller-history':['id']}
   if name not in required or set(q)!=set(required[name]) or any(len(v)!=1 for v in q.values()):raise ValueError('Exact supported query fields required')
   if name=='bootstrap':value={**s.catalog(),'csrf_token':self.server.token}
   elif name=='project':value=s.read(q['id'][0])
   elif name=='run':value=s.run(q['id'][0],q['nonce'][0])
   elif name=='controller-run':value=s.controllers.run(q['id'][0],q['nonce'][0])
   elif name=='controller-report':value=s.controllers.report(q['id'][0],q['nonce'][0])
   elif name=='controller-history':value=s.controllers.history(q['id'][0])
   else:value=s.report(q['id'][0],q['nonce'][0])
   self.reply(200,value)
  except PermissionError:self.reply(403,{'error':'Local same-origin authority required'})
  except (ValueError,ValidationError) as e:self.reply(400,{'error':str(e)[:240]})
  except (OSError,KeyError):self.reply(400,{'error':'Local project/evidence unavailable or invalid; no fallback or execution'})
  except Exception:self.reply(500,{'error':'Local operation failed; no retry was performed'})
 def do_POST(self):
  route=urlsplit(self.path)
  if not route.path.startswith('/api/workbench/'):return super().do_POST()
  try:
   self.guard(write=True)
   if route.query or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':raise ValueError('Exact bounded JSON request required')
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=24000:raise ValueError('Request limit is24000 bytes')
   self.connection.settimeout(10);b=decode_json(self.rfile.read(size));name=route.path.removeprefix('/api/workbench/');s=self.service()
   fields={'create':['title'],'review':['id','expected','source'],'decide':['id','expected','review_id','decision','confirmation'],'restore':['id','expected','review_id'],'start':['id','expected','nonce','confirmation'],'cancel':['id','nonce'],'explain':['id','nonce','question'],'suggest':['id','expected','nonce']}
   fields.update({'controller-create':['title'],'controller-tool':['id','expected','controller_head','name','arguments'],'controller-decide':['id','expected','controller_head','review_id','decision','confirmation'],'controller-restore':['id','expected','controller_head','snapshot'],'controller-start':['id','expected','controller_head','nonce','confirmation'],'controller-cancel':['id','nonce'],'controller-offline':['id','expected','controller_head','task','nonce'],'controller-explain':['id','nonce']})
   if name not in fields:raise PermissionError('No provider, credentials, arbitrary source, backend approval or mechanical apply endpoint')
   exact(b,fields[name])
   if name=='controller-create':value=s.controllers.create(b['title'])
   elif name=='controller-tool':value=s.controllers.tool(b['id'],b['expected'],b['controller_head'],b['name'],b['arguments'])
   elif name=='controller-decide':value=s.controllers.decide(b['id'],b['expected'],b['controller_head'],b['review_id'],b['decision'],b['confirmation'])
   elif name=='controller-restore':value=s.controllers.restore(b['id'],b['expected'],b['controller_head'],b['snapshot'])
   elif name=='controller-start':value=s.controllers.start(b['id'],b['expected'],b['controller_head'],b['nonce'],b['confirmation'],self.server.job)
   elif name=='controller-cancel':value=s.controllers.cancel(b['id'],b['nonce'])
   elif name=='controller-offline':value=s.controllers.offline(b['id'],b['expected'],b['controller_head'],b['task'],b['nonce'])
   elif name=='controller-explain':value=s.controllers.explain(b['id'],b['nonce'])
   elif name=='create':value=s.create(b['title'])
   elif name=='review':value=s.review(b['id'],b['expected'],b['source'])
   elif name=='decide':value=s.decide(b['id'],b['expected'],b['review_id'],b['decision'],b['confirmation'])
   elif name=='restore':value=s.restore(b['id'],b['expected'],b['review_id'])
   elif name=='start':value=s.start(b['id'],b['expected'],b['nonce'],b['confirmation'],self.server.job)
   elif name=='cancel':value=s.cancel(b['id'],b['nonce'])
   elif name=='explain':value=s.explain(b['id'],b['nonce'],b['question'])
   else:value=s.suggest(b['id'],b['expected'],b['nonce'])
   self.reply(200,value)
  except PermissionError:self.reply(403,{'error':'Explicit local confirmation and same-origin authority required'})
  except (ValueError,ValidationError,TypeError) as e:self.reply(400,{'error':str(e)[:240]})
  except (OSError,KeyError):self.reply(400,{'error':'Local project/evidence unavailable or invalid; no fallback or execution'})
  except Exception:self.reply(500,{'error':'Local operation failed; no automatic retry'})

class WorkbenchServer(EngineeringServer):
 def __init__(self,*a,workbench=None,**k):
  super().__init__(*a,**k);self.RequestHandlerClass=WorkbenchHandler
  if workbench is not None:self.workbench=workbench

def main():
 p=argparse.ArgumentParser(description='EMBODY local trusted engineering workspace; no provider startup');p.add_argument('--port',type=int,default=8765);p.add_argument('--check',action='store_true');a=p.parse_args()
 from ide_api.startup import check
 try:
  ready=check()
  if a.check:print(json.dumps(ready));return
  if not 1<=a.port<=65535:raise ValueError('Choose a valid loopback port')
  server=WorkbenchServer(('127.0.0.1',a.port))
 except (ValueError,OSError) as e:p.exit(2,'Cannot start EMBODY: '+str(e)+'\nNo installation, model request or simulation was performed.\n')
 def stop(*unused):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,stop);print(f'EMBODY local workspace: http://{server.host}',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()

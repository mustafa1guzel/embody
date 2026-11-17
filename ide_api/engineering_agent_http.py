"""Explicit extension of the existing loopback server, not another executor.

Base Handler.guard, reply headers and every legacy route are preserved. Native-
bound server.py remains unchanged; this entrypoint joins broader app binding.
"""
import argparse,json,signal
from urllib.parse import urlsplit
from ide_api.server import Server,Handler,exact
from workspace.data import decode_json
from jsonschema import ValidationError

class EngineeringHandler(Handler):
 def do_GET(self):
  if not self.path.startswith('/api/engineering-agent/'):return super().do_GET()
  try:self.guard();return self.reply(400,{'error':'Engineering context/tools require exact POST with same-origin token; arbitrary read queries are unsupported'})
  except PermissionError:return self.reply(403,{'error':'Loopback same-origin required'})
 def do_POST(self):
  if not self.path.startswith('/api/engineering-agent/'):return super().do_POST()
  try:
   self.guard(write=True)
   if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':raise ValueError('Exact bounded JSON body required')
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=24000:raise ValueError('Engineering request size exceeded')
   self.connection.settimeout(10);body=decode_json(self.rfile.read(length));route=urlsplit(self.path)
   if route.query:raise ValueError('Unexpected query fields')
   ide=self.server.ide
   from ide_api.toolkit import Toolkit
   from ide_api.product_alpha import ProductAlpha
   from ide_api.engineering_agent import EngineeringAgent
   with self.server.jobs_guard:
    if not hasattr(ide,'_toolkit'):ide._toolkit=Toolkit()
    if not hasattr(ide,'_product_alpha'):ide._product_alpha=ProductAlpha(ide.experiment_designer)
    if not hasattr(ide,'_engineering_agent'):ide._engineering_agent=EngineeringAgent(ide._product_alpha,ide._toolkit)
   service=ide._engineering_agent
   if route.path=='/api/engineering-agent/context':exact(body,['context']);result=service.context(body['context'])
   elif route.path=='/api/engineering-agent/tool':
    exact(body,['context','expected_context','name','arguments']);result=service.dispatch(body['context'],body['expected_context'],body['name'],body['arguments'],human=body['name']=='review_proposal')
   else:raise PermissionError('No provider, approval, execution, save or apply endpoint exists in this namespace')
   return self.reply(200,result)
  except PermissionError:self.reply(403,{'error':'Explicit same-origin human authority required; no action executed'})
  except (OSError,KeyError):self.reply(400,{'error':'Registered context, proposal or evidence is unavailable; no path lookup or fallback is permitted','status':'REJECTED_NO_EXECUTION'})
  except (ValueError,TypeError,ValidationError) as exc:
   self.reply(400,{'error':exc.message[:240] if isinstance(exc,ValidationError) else str(exc)[:240],'status':'REJECTED_NO_EXECUTION'})
  except Exception:self.reply(500,{'error':'Engineering tool unavailable; no fallback or automatic retry'})

class EngineeringServer(Server):
 def __init__(self,*a,**k):
  super().__init__(*a,**k);self.RequestHandlerClass=EngineeringHandler

def main():
 parser=argparse.ArgumentParser(description='Existing EMBODY local product with bounded engineering assistant tools; no live provider execution.')
 parser.add_argument('--port',type=int,default=8765);parser.add_argument('--check',action='store_true');args=parser.parse_args()
 try:
  if not 1<=args.port<=65535:raise ValueError('Choose a port from 1 to 65535')
  from ide_api.startup import check
  ready=check()
  if args.check:print(json.dumps(ready,indent=2));return
  server=EngineeringServer(('127.0.0.1',args.port))
 except (ValueError,OSError) as exc:parser.exit(2,'Cannot start EMBODY: '+str(exc)+'\nNo process was stopped and no dependency installed.\n')
 def stop(*unused):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,stop);print(f'EMBODY IDE: http://127.0.0.1:{server.server_port} (engineering tools; no paid/native startup)',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()

"""v1.0 test-only guard: trusted native physics allowed, paid/VM/history writes denied.

Not a containment certificate or a product sandbox. No provider credentials are
read; explicit temporary dummy credential fixtures remain valid unit tests.
"""
import json,os,socket,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COUNTS={'native_mj_step_calls':0,'native_mj_forward_calls':0,'external_network_attempts':0,'VM_launch_attempts':0,'historical_write_attempts':0,'real_credential_attempts':0}
RESTORE=[]
def pytest_sessionstart(session):
 import mujoco
 from core.agent import credentials
 inventory=json.loads(Path(os.environ['EMBODY_V100_BASELINE']).read_text())
 protected={str(Path(n) if n.startswith('/') else ROOT/n) for n in inventory['historical_files']}
 def audit(event,args):
  if event=='socket.connect':
   address=args[1]
   if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
    COUNTS['external_network_attempts']+=1;raise PermissionError('v1 tests forbid outbound network')
  if event=='subprocess.Popen':
   exe=str(args[0]);argv=args[1]
   if any(x in exe.lower() for x in ('qemu','docker','podman')) or Path(exe).name=='container' and any(x in argv for x in ('run','start','create')):
    COUNTS['VM_launch_attempts']+=1;raise PermissionError('v1 tests forbid VM/container launches')
  if event=='open':
   name,mode,flags=args
   write=isinstance(mode,str) and any(c in mode for c in 'wax+') or (flags or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)
   if not isinstance(name,(str,bytes,os.PathLike)) or not write:return
   p=str(Path(os.fsdecode(name)).absolute())
   if p in protected or p.startswith(str(ROOT/'.runtime/engineering_agent_live')+'/') or p.startswith(str(ROOT.with_name('embody'))+'/'):
    COUNTS['historical_write_attempts']+=1;raise PermissionError('Historical/original workspaces are read-only in v1 tests')
 def credential_guard(env_path=None):
  actual=Path(env_path) if env_path is not None else credentials.PROJECT_ENV_PATH
  if actual.absolute() in (ROOT/'.env',ROOT.with_name('embody')/'.env'):
   COUNTS['real_credential_attempts']+=1;raise PermissionError('Actual credential access forbidden in v1 tests')
  return original_reader(env_path)
 original_reader=credentials.read_openai_api_key;RESTORE.append((credentials,'read_openai_api_key',original_reader));credentials.read_openai_api_key=credential_guard
 for name,key in [('mj_step','native_mj_step_calls'),('mj_forward','native_mj_forward_calls')]:
  fn=getattr(mujoco,name)
  def measured(*a,_fn=fn,_key=key,**k):COUNTS[_key]+=1;return _fn(*a,**k)
  RESTORE.append((mujoco,name,fn));setattr(mujoco,name,measured)
 sys.addaudithook(audit)

def pytest_sessionfinish(session,exitstatus):
 for obj,name,old in reversed(RESTORE):setattr(obj,name,old)
 p=Path(os.environ['EMBODY_V100_GUARD_OUTPUT'])
 with p.open('x') as f:json.dump({'test_guard_counters':COUNTS,'trusted_native_development_scope':True,'paid_requests':0,'VM_launches':0,'instrumentation_not_security_qualification':True},f,indent=2);f.write('\n')

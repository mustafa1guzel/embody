"""Opt-in pytest release guard. Runtime instrumentation is not security qualification."""
import json,os
from pathlib import Path

COUNTERS={'native_integration_attempts':0,'paid_provider_attempts':0,'vm_attempts':0,'apply_attempts':0}
RESTORE=[]
def deny(name):
 def blocked(*args,**kwargs):
  COUNTERS[name]+=1
  raise AssertionError('Ordinary release verification forbids '+name)
 return blocked

def install():
 import mujoco
 from core.agent import credentials,vm_backend
 from ide_api.engineering import EngineeringService
 for obj,name,category in [(mujoco,'mj_step','native_integration_attempts'),(mujoco,'mj_step1','native_integration_attempts'),(mujoco,'mj_step2','native_integration_attempts'),(credentials,'create_openai_client','paid_provider_attempts'),(vm_backend,'runtime_command','vm_attempts'),(EngineeringService,'decide','apply_attempts')]:
  RESTORE.append((obj,name,getattr(obj,name)));setattr(obj,name,deny(category))

def pytest_sessionstart(session):install()
def pytest_sessionfinish(session,exitstatus):
 path=os.environ.get('EMBODY_VERIFICATION_GUARD_OUTPUT')
 if path:
  with Path(path).open('x') as f:json.dump({'counters':COUNTERS,'native_steps':0,'paid_requests':0,'vm_launches':0,'automatic_applications':0,'method':'Actual forbidden entry points instrumented; attempts counted before refusal.'},f,indent=2)
 if any(COUNTERS.values()):session.exitstatus=1
 for obj,name,original in reversed(RESTORE):setattr(obj,name,original)

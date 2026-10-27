"""Fail-closed Apple per-container-VM transport. No shell or host candidate import."""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
from uuid import uuid4

import mujoco
import numpy as np

from core.agent.vm_protocol import VERSION, MAX_FRAME, ProtocolError, encode, decode, command_reply
from core.simulation import ROOT

DEFAULT_CONFIG = ROOT / '.runtime/day4b1/backend.json'

class IsolationBlocked(RuntimeError):
    pass

def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1048576): digest.update(chunk)
    return digest.hexdigest()

def clean_environment(config):
    # No caller environment forwarding, including API keys, proxies or SSH sockets.
    return {'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
            'CONTAINER_APP_ROOT': config['app_root'], 'CONTAINER_INSTALL_ROOT': config['install_root'],
            'XDG_CONFIG_HOME': config['config_home']}

def runtime_command(config, args, timeout=15):
    try:
        result=subprocess.run([config['runtime'], *args],env=clean_environment(config),
                              capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise IsolationBlocked('Runtime is unavailable or exceeded its control-operation deadline') from exc
    if result.returncode:
        raise IsolationBlocked('Runtime operation failed: '+result.stderr[:512])
    return result.stdout

def identity(config):
    files = sorted((ROOT/'core').rglob('*.py'))
    files += sorted((ROOT/'configs').glob('*.json'))
    files += [ROOT/'robot/controller.py', ROOT/'robot/rail_carriage.xml']
    # New family safety inputs and deterministic evaluators are qualification-bound.
    files += [ROOT/'robot/arm_controller.py', ROOT/'robot/planar_arm.xml']
    files += sorted((ROOT/'physics').glob('*.py'))
    files += [ROOT/'workspace/workflow.py',ROOT/'workspace/data.py']
    files += [Path(config['runtime']),Path(config['kernel'])]
    files += sorted(p for p in Path(config['install_root']).rglob('*') if p.is_file() and not p.is_symlink())
    return {'files': {str(p.relative_to(ROOT)):file_hash(p) for p in files},
            'configuration_sha256':hashlib.sha256(encode(config)).hexdigest()}

def inspect_pinned(config, key):
    reference=config[key]
    tag=config[key+'_local_tag']
    items=json.loads(runtime_command(config,['image','inspect',tag]))
    expected=reference.split('@',1)[1]
    if len(items)!=1 or items[0]['configuration']['descriptor']['digest']!=expected:
        raise IsolationBlocked('Pinned local image is absent or changed')
    return items[0]

class VMProcess:
    """Internal transport. Direct use is reserved for developer-authored containment probes."""
    def __init__(self,config,*,wall_seconds=60,cpu_seconds=30):
        self.config=config
        self.wall_seconds=wall_seconds
        self.cpu_seconds=cpu_seconds
        self.name='embody-'+uuid4().hex
        self.process=None
        self.buffer=b''
        self.stderr=bytearray()
        self.cleaned=False

    def __enter__(self):
        for key in ('image', 'init_image'):
            inspect_pinned(self.config, key)
        self.lock=open(Path(self.config['app_root'])/'embody-execution.lock','a+b')
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            raise IsolationBlocked('Another VM execution owns the single-worker lock') from exc
        args=['run','--name',self.name,'--network','none','--no-dns','--read-only',
              '--cpus','1','--memory','1g','--user','65532:65532','--cap-drop','ALL',
              '--tmpfs','/tmp:size=32m,nosuid,nodev,noexec,mode=1777','--shm-size','8m',
              '--ulimit',f'cpu={self.cpu_seconds}','--ulimit','nproc=16','--ulimit','nofile=64',
              '--ulimit','core=0','--ulimit','fsize=33554432',
              '--kernel',self.config['kernel'],'--init-image',self.config['init_image'],
              '-i',self.config['image']]
        self.command=[self.config['runtime'],*args]
        self.deadline=time.monotonic()+self.wall_seconds
        try:
            self.process=subprocess.Popen(self.command,env=clean_environment(self.config),stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            self.selector=selectors.DefaultSelector()
            for stream in (self.process.stdout,self.process.stderr):
                os.set_blocking(stream.fileno(),False)
                self.selector.register(stream,selectors.EVENT_READ)
            return self
        except Exception:
            self.close()
            raise

    def send(self,value):
        raw=encode(value)
        # Requests are bounded; a nonreading worker must not block host writes.
        fd=self.process.stdin.fileno()
        os.set_blocking(fd,False)
        sent=0
        while sent<len(raw):
            if time.monotonic()>=self.deadline:
                raise TimeoutError('Host VM execution deadline exceeded while sending')
            try: sent+=os.write(fd,raw[sent:])
            except BlockingIOError:
                time.sleep(.001)
        return self.receive()

    def receive(self):
        while True:
            if b'\n' in self.buffer:
                raw,self.buffer=self.buffer.split(b'\n',1)
                return decode(raw+b'\n')
            if len(self.buffer)>MAX_FRAME:
                raise ProtocolError('Worker output exceeds frame limit')
            remaining=self.deadline-time.monotonic()
            if remaining<=0: raise TimeoutError('Host VM execution deadline exceeded')
            events=self.selector.select(min(remaining,.1))
            for key,_ in events:
                chunk=os.read(key.fileobj.fileno(),min(65536,MAX_FRAME+1))
                if not chunk:
                    self.selector.unregister(key.fileobj)
                    continue
                if key.fileobj is self.process.stdout:
                    self.buffer+=chunk
                else:
                    self.stderr.extend(chunk)
                    if len(self.stderr)>1_048_576: raise ProtocolError('Worker stderr budget exceeded')
            if not self.selector.get_map():
                raise ProtocolError('Worker exited without a complete reply: '+self.stderr.decode(errors='replace')[:512])

    def close(self):
        errors=[]
        # Killing the CLI alone does not terminate a VM. Explicitly kill/delete the named VM.
        for args in (['kill','--signal','KILL',self.name],['delete','--force',self.name]):
            try:
                runtime_command(self.config,args,timeout=15)
            except IsolationBlocked as exc:
                # Absence is checked independently below, including failed startup.
                errors.append(str(exc))
        if self.process is not None:
            if self.process.poll() is None:
                os.killpg(self.process.pid,signal.SIGKILL)
            self.process.wait(timeout=5)
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr):stream.close()
        if hasattr(self,'selector'): self.selector.close()
        try:
            listing=json.loads(runtime_command(self.config,['list','--all','--format','json']))
            if not isinstance(listing,list):raise IsolationBlocked('Invalid runtime container inventory')
            self.cleaned=not any(row.get('id')==self.name or row.get('configuration',{}).get('id')==self.name for row in listing)
        except Exception:
            self.cleaned=False
        if hasattr(self,'lock') and not self.lock.closed:
            fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close()
        if not self.cleaned:
            Path(self.config['certificate']).unlink(missing_ok=True)
            raise IsolationBlocked('VM cleanup could not be independently confirmed; qualification revoked')

    def __exit__(self,*_): self.close()

class AppleVMBackend:
    def __init__(self,config_path=DEFAULT_CONFIG):
        self.config_path=Path(config_path)
        self.config=json.loads(self.config_path.read_text())

    def preflight(self):
        c=self.config
        if not all(isinstance(c.get(k),str) for k in ('runtime','kernel','image','init_image','image_local_tag','init_image_local_tag','app_root','install_root','config_home','certificate')):
            raise IsolationBlocked('Invalid operator configuration')
        for key in ('runtime','kernel','app_root','install_root','config_home','certificate'):
            if not Path(c[key]).resolve().is_relative_to(ROOT/'.runtime/day4b1'):
                raise IsolationBlocked('Runtime configuration escaped the dedicated local installation')
        if '@sha256:' not in c['image'] or '@sha256:' not in c['init_image']:
            raise IsolationBlocked('Images must be pinned by digest')
        try: proof=json.loads(Path(c['certificate']).read_text())
        except (OSError,ValueError) as exc: raise IsolationBlocked('Containment certificate is absent') from exc
        if proof.get('status')!='PASS' or proof.get('identity')!=identity(c):
            raise IsolationBlocked('Containment evidence is stale, failed, or mismatched')
        age=time.time()-proof.get('created_unix',0)
        if not 0<=age<=86400: raise IsolationBlocked('Containment evidence expired; repeat probes')
        result=subprocess.run(['/usr/bin/codesign','--verify','--strict',c['runtime']],capture_output=True,timeout=15)
        if result.returncode: raise IsolationBlocked('Runtime code signature verification failed')
        if '1.6.0' not in runtime_command(c,['--version']): raise IsolationBlocked('Runtime version changed')
        # Both digests must already be in the local store. Never permit runtime auto-pulls.
        for key in ('image','init_image'):
            inspect_pinned(c,key)
        listing=json.loads(runtime_command(c,['list','--all','--format','json']))
        if not isinstance(listing,list):raise IsolationBlocked('Invalid runtime container inventory')
        if listing: raise IsolationBlocked('Dedicated runtime contains another container')
        return proof

    @contextmanager
    def controller(self,source,xml):
        self.preflight()
        with VMProcess(self.config) as vm:
            ready=vm.send({'v':VERSION,'source':source,'sha256':hashlib.sha256(source.encode()).hexdigest(),'xml':xml})
            expected_model=mujoco.MjModel.from_xml_string(xml)
            size=mujoco.mj_stateSize(expected_model,mujoco.mjtState.mjSTATE_INTEGRATION)
            if (set(ready)!=set(('v','ready','mujoco','state_size','xml_sha256','mass','force'))
                    or ready['v']!=VERSION or ready['ready'] is not True or ready['mujoco']!=mujoco.__version__
                    or ready['xml_sha256']!=hashlib.sha256(xml.encode()).hexdigest() or ready['state_size']!=size
                    or ready['mass']!=float(expected_model.body('carriage').mass[0])
                    or ready['force']!=expected_model.actuator_forcerange.tolist()):
                raise ProtocolError('Worker MuJoCo handshake mismatch')
            exchanges=[]
            def remote_controller(model,data):
                state=np.empty(size,dtype=np.float64)
                mujoco.mj_getState(model,data,state,mujoco.mjtState.mjSTATE_INTEGRATION)
                seq=len(exchanges)
                request={'v':VERSION,'seq':seq,'state':state.tolist()}
                reply=vm.send(request)
                command=command_reply(reply,seq,model.nu)
                data.ctrl[:]=command
                exchanges.append({'seq':seq,'state':request['state'],'ctrl':command})
            yield remote_controller,exchanges,ready

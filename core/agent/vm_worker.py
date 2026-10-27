"""Linux-only worker entry point. Candidate source is executed ONLY inside its VM.

The host treats all output as untrusted actuator requests, never safety evidence.
Developer probes are fixed code used before the execution gate is enabled.
"""
import hashlib
import ctypes
import errno
import json
import math
import os
from pathlib import Path
import resource
import socket
import sys
import time

sys.path.insert(0, '/opt/embody')
from vm_protocol import VERSION, MAX_FRAME, decode, encode, fields, numbers

def send(value):
    sys.stdout.buffer.write(encode(value))
    sys.stdout.buffer.flush()

def receive():
    return decode(sys.stdin.buffer.readline(MAX_FRAME + 1))

def probe(name):
    if name == 'inventory':
        mount = Path('/proc/self/mountinfo').read_text()
        group=Path('/proc/self/cgroup').read_text().strip().split(':')[-1]
        cg=Path('/sys/fs/cgroup')/group.lstrip('/')
        limits={k:(cg/k).read_text().strip() for k in ('cpu.max','memory.max','pids.max') if (cg/k).exists()}
        send({'uid': os.getuid(), 'env_keys': sorted(os.environ),
              'worker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol_sha256':hashlib.sha256(Path('/opt/embody/vm_protocol.py').read_bytes()).hexdigest(),
              'helper_sha256':hashlib.sha256(Path('/opt/embody/core/simulation.py').read_bytes()).hexdigest(),
              'cpus': len(os.sched_getaffinity(0)),
              'memory_bytes': os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE'),
              'limits': {k: list(resource.getrlimit(getattr(resource, 'RLIMIT_' + k)))
                         for k in ('CPU', 'AS', 'NPROC', 'NOFILE', 'CORE')},
              'mountinfo': mount, 'interfaces': sorted(os.listdir('/sys/class/net')),
              'status': Path('/proc/self/status').read_text(), 'cgroup':group, 'cgroup_limits':limits})
    elif name == 'filesystem':
        checks = {}
        for path in ('/opt/embody/probe-writable', '/etc/embody-forbidden', '/host/README.md',
                     '/Users/Shared/embody-host-canary', '/private/tmp/embody-host-canary'):
            try:
                with open(path, 'r+b') as handle:
                    handle.write(b'X')
                checks[path] = 'ACCESSIBLE'
            except OSError as exc:
                checks[path] = exc.errno
        send(checks)
    elif name == 'network':
        result = []
        for family, address in ((socket.AF_INET, ('1.1.1.1', 443)),
                                 (socket.AF_INET, ('192.168.64.1', 80)),
                                 (socket.AF_INET6, ('2606:4700:4700::1111', 443))):
            try:
                with socket.socket(family) as sock:
                    sock.settimeout(.2)
                    sock.connect(address)
                result.append('CONNECTED')
            except OSError as exc:
                result.append({'errno':exc.errno,'name':errno.errorcode.get(exc.errno,'UNKNOWN')})
        send({'attempts': result})
    elif name == 'scratch':
        written = 0
        try:
            with open('/tmp/fill', 'wb') as handle:
                for _ in range(40):
                    handle.write(b'X' * 1_048_576)
                    handle.flush()
                    written += 1_048_576
        except OSError as exc:
            send({'written': written, 'errno': exc.errno})
    elif name == 'memory':
        try:
            value = bytearray(1_073_741_824)
            send({'allocation': len(value)})
        except MemoryError:
            send({'allocation': 'DENIED'})
    elif name == 'memory_group':
        group=Path('/proc/self/cgroup').read_text().strip().split(':')[-1]
        events=Path('/sys/fs/cgroup')/group.lstrip('/')/'memory.events'
        def kills():
            return int(dict(line.split() for line in events.read_text().splitlines())['oom_kill'])
        before=kills()
        children=[]
        for _ in range(3):
            pid=os.fork()
            if pid==0:
                value=bytearray(400*1024*1024)
                time.sleep(3)
                os._exit(0)
            children.append(pid)
        statuses=[os.waitpid(pid,0)[1] for pid in children]
        send({'oom_kill_before':before,'oom_kill_after':kills(),'child_statuses':statuses})
    elif name == 'processes':
        children=[];denial=None
        try:
            for _ in range(20):
                pid=os.fork()
                if pid==0:
                    time.sleep(30)
                    os._exit(0)
                children.append(pid)
        except OSError as exc:
            denial=errno.errorcode.get(exc.errno)
        finally:
            for pid in children:
                os.kill(pid,9)
                os.waitpid(pid,0)
        send({'spawned':len(children),'denial':denial})
    elif name == 'files':
        handles=[];denial=None
        try:
            for _ in range(80):handles.append(open('/dev/null','rb'))
        except OSError as exc:denial=errno.errorcode.get(exc.errno)
        finally:
            for handle in handles:handle.close()
        send({'opened':len(handles),'denial':denial})
    elif name == 'cpu':
        send({'started': True, 'cpu_limit': list(resource.getrlimit(resource.RLIMIT_CPU))})
        while True:
            pass
    elif name == 'timeout':
        time.sleep(120)
    elif name == 'descendant':
        pid = os.fork()
        if pid == 0:
            time.sleep(120)
            os._exit(0)
        send({'child_started': pid > 0})
        time.sleep(120)
    elif name == 'invalid':
        sys.stdout.buffer.write(b'{"v":1,"seq":0,"ctrl":[NaN]}\n')
        sys.stdout.buffer.flush()
    elif name == 'oversized':
        sys.stdout.buffer.write(b'X' * (MAX_FRAME + 1))
        sys.stdout.buffer.flush()
    else:
        raise ValueError('Unknown developer probe')

def main():
    if ctypes.CDLL(None).prctl(38,1,0,0,0)!=0:  # PR_SET_NO_NEW_PRIVS: irreversible for descendants.
        raise RuntimeError('Could not prohibit privilege escalation')
    # Hard cap inherited by candidate and descendants; VM RAM also bounds their aggregate.
    resource.setrlimit(resource.RLIMIT_AS, (805_306_368, 805_306_368))
    first = receive()
    if set(first) == {'probe'}:
        probe(first['probe'])
        return
    fields(first, ('v', 'source', 'sha256', 'xml'))
    if first['v'] != VERSION or not isinstance(first['source'], str) or len(first['source'].encode()) > 100_000:
        raise ValueError('Invalid source request')
    if not isinstance(first['xml'], str) or len(first['xml'].encode()) > 65_536:
        raise ValueError('Invalid model request')
    if hashlib.sha256(first['source'].encode()).hexdigest() != first['sha256']:
        raise ValueError('Candidate hash mismatch')
    import mujoco
    import numpy as np
    from core.simulation import collision_surfaces
    model = mujoco.MjModel.from_xml_string(first['xml'])
    data = mujoco.MjData(model)
    namespace = {'__name__': 'isolated_candidate'}
    # This file is included in the Linux image and is never run on the host.
    exec(compile(first['source'], '<isolated-candidate>', 'exec'), namespace)
    controller = namespace['faulty_braking_controller']
    signature = mujoco.mjtState.mjSTATE_INTEGRATION
    size = mujoco.mj_stateSize(model, signature)
    send({'v': VERSION, 'ready': True, 'mujoco': mujoco.__version__, 'state_size': size,
          'xml_sha256': hashlib.sha256(first['xml'].encode()).hexdigest(),
          'mass': float(model.body('carriage').mass[0]), 'force': model.actuator_forcerange.tolist()})
    seq = 0
    while True:
        request = receive()
        fields(request, ('v', 'seq', 'state'))
        if request['v'] != VERSION or type(request['seq']) is not int or request['seq'] != seq:
            raise ValueError('Out-of-sequence state')
        state = np.array(numbers(request['state'], size), dtype=np.float64)
        mujoco.mj_setState(model, data, state, signature)
        mujoco.mj_forward(model, data)
        controller(model, data)
        send({'v': VERSION, 'seq': seq, 'ctrl': data.ctrl.tolist()})
        seq += 1

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        sys.stderr.write(type(exc).__name__ + ': ' + str(exc)[:256] + '\n')
        sys.exit(2)

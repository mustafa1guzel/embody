"""Assemble pinned OCI images locally, without executing guest code or BuildKit."""
import gzip
import hashlib
import inspect
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.simulation import collision_surfaces
from tools.day4b1_provision import cached

BASE = ROOT / '.runtime/day4b1'
OUT = ROOT / 'artifacts/day4b1/implementation'
PLAN = json.loads((OUT / 'download_plan.json').read_text())
BLOBS = BASE / 'downloads/blobs'

def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()

def json_bytes(value):
    return json.dumps(value, separators=(',', ':')).encode()

def blob(data):
    name = digest(data)
    (BLOBS / name.split(':')[1]).write_bytes(data)
    return name

def archive(image, path, tag):
    manifest = image['manifest']
    manifest_raw = image.get('manifest_text', json.dumps(manifest, separators=(',', ':'))).encode()
    manifest_digest = blob(manifest_raw)
    entries = {'oci-layout': b'{"imageLayoutVersion":"1.0.0"}',
               'index.json': json_bytes({'schemaVersion':2,'manifests':[
                   {'mediaType':'application/vnd.oci.image.manifest.v1+json', 'digest':manifest_digest,
                    'size':len(manifest_raw),'annotations':{'org.opencontainers.image.ref.name':tag},
                    'platform':{'architecture':'arm64','os':'linux'}}]})}
    with tarfile.open(path, 'w') as tar:
        for name, data in entries.items():
            info=tarfile.TarInfo(name); info.size=len(data); tar.addfile(info,io.BytesIO(data))
        for item in [manifest['config'], *manifest['layers'], {'digest':manifest_digest}]:
            file=BLOBS/item['digest'].split(':')[1]
            if not cached(file,item['digest']):raise ValueError('Cached OCI blob digest mismatch')
            tar.add(file,arcname='blobs/sha256/'+file.name,recursive=False)
    return manifest_digest

def main():
    init = PLAN['images'][0]
    init_digest = archive(init, BASE/'init.oci.tar', 'ghcr.io/apple/containerization/vminit:0.52.1')
    files = {}
    for wheel in PLAN['wheels']:
        if not cached(BASE/'downloads'/wheel['filename'],wheel['sha256']):raise ValueError('Cached wheel digest mismatch')
        with zipfile.ZipFile(BASE/'downloads'/wheel['filename']) as zipf:
            for member in zipf.infolist():
                path=PurePosixPath(member.filename)
                if path.is_absolute() or '..' in path.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe wheel path')
                if member.is_dir(): continue
                parts=path.parts
                if parts[0].endswith('.data'):
                    if parts[1] not in ('purelib','platlib'):
                        raise ValueError('Unsupported wheel data path')
                    path=PurePosixPath(*parts[2:])
                files['usr/local/lib/python3.12/site-packages/'+str(path)] = (zipf.read(member),0o644)
    files['opt/embody/core/__init__.py']=(b'',0o644)
    helper=('import mujoco\nimport numpy as np\n'+inspect.getsource(collision_surfaces)).encode()
    files['opt/embody/core/simulation.py']=(helper,0o644)
    for name in ('vm_protocol.py','vm_worker.py'):
        files['opt/embody/'+name]=((ROOT/'core/agent'/name).read_bytes(),0o644)
    files['opt/embody/probe-writable']=(b'read-only filesystem canary\n',0o666)
    layer=BASE/'worker-layer.tar'
    with tarfile.open(layer,'w') as tar:
        for name,(data,mode) in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;info.mtime=0
            tar.addfile(info,io.BytesIO(data))
    raw=layer.read_bytes()
    compressed=gzip.compress(raw,mtime=0)
    layer_digest=blob(compressed)
    base=PLAN['images'][1]
    config=json.loads((BLOBS/base['manifest']['config']['digest'].split(':')[1]).read_text())
    config['rootfs']['diff_ids'].append(digest(raw))
    config['config'].update({'Entrypoint':['/usr/local/bin/python','-I','-u','/opt/embody/vm_worker.py'],
                             'Cmd':[], 'User':'65532:65532', 'WorkingDir':'/tmp',
                             'Env':['PATH=/usr/local/bin:/usr/bin:/bin','HOME=/tmp','MUJOCO_GL=disable',
                                    'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','PYTHONDONTWRITEBYTECODE=1']})
    cfg_raw=json_bytes(config);cfg_digest=blob(cfg_raw)
    manifest={'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
              'config':{'mediaType':'application/vnd.oci.image.config.v1+json','digest':cfg_digest,'size':len(cfg_raw)},
              'layers':base['manifest']['layers']+[{'mediaType':'application/vnd.oci.image.layer.v1.tar+gzip',
                                                  'digest':layer_digest,'size':len(compressed)}]}
    image={'manifest':manifest}
    worker_digest=archive(image,BASE/'worker.oci.tar','localhost/embody-worker:day4b1')
    result={'worker_digest':worker_digest,'init_digest':init_digest,'worker_layer_bytes':len(compressed),
            'worker_layer_uncompressed_bytes':len(raw), 'worker_image_bytes':(BASE/'worker.oci.tar').stat().st_size,
            'init_archive_bytes':(BASE/'init.oci.tar').stat().st_size,
            'helper_sha256':hashlib.sha256(helper).hexdigest(),
            'worker_source_sha256':hashlib.sha256((ROOT/'core/agent/vm_worker.py').read_bytes()).hexdigest(),
            'protocol_source_sha256':hashlib.sha256((ROOT/'core/agent/vm_protocol.py').read_bytes()).hexdigest()}
    (OUT/'images.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()

"""Load verified offline artifacts into the signed user-local Apple runtime."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.agent.vm_backend import runtime_command,file_hash

def main():
    base=ROOT/'.runtime/day4b1'
    config=json.loads((base/'backend.json').read_text())
    plan=json.loads((ROOT/'artifacts/day4b1/implementation/download_plan.json').read_text())
    images=json.loads((ROOT/'artifacts/day4b1/implementation/images.json').read_text())
    report={}
    for kind in ('runtime','kernel'):
        asset=plan[kind]
        if file_hash(base/'downloads'/asset['name'])!=asset['published_sha256'].removeprefix('sha256:'):
            raise RuntimeError('Cached approved artifact digest changed')
    signatures=[]
    for binary in (base/'package/Payload').rglob('*'):
        if binary.is_file() and binary.stat().st_mode&0o111:
            with binary.open('rb') as f:magic=f.read(4)
            if magic not in (b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe'):continue
            result=subprocess.run(['/usr/bin/codesign','--verify','--strict',str(binary)],capture_output=True,text=True,check=True)
            signatures.append({'path':str(binary.relative_to(ROOT)),'sha256':file_hash(binary),'code_signature':'PASS'})
    report['signed_binaries']=signatures
    report['installation_mode']='User-local unchanged official signed package payload; no root installer receipt'
    for key,archive,tag,expected in (
        ('init_image','init.oci.tar','ghcr.io/apple/containerization/vminit:0.52.1',images['init_digest']),
        ('image','worker.oci.tar','localhost/embody-worker:day4b1',images['worker_digest'])):
        runtime_command(config,['image','load','--input',str(base/archive)],timeout=60)
        item=json.loads(runtime_command(config,['image','inspect',tag]))[0]
        if len(item['variants'])!=1 or item['variants'][0]['digest']!=expected:
            raise RuntimeError('Loaded image differs from the locally verified manifest')
        # Import canonicalizes the OCI index. Pin that index and retain its verified child manifest.
        config[key]=tag.rsplit(':',1)[0]+'@'+item['configuration']['descriptor']['digest']
        config[key+'_local_tag']=tag
        runtime_command(config,['image','tag',tag,config[key]])
        report[key]={'local_index_digest':item['configuration']['descriptor']['digest'],
                     'verified_manifest_digest':expected,'local_archive_bytes':(base/archive).stat().st_size}
    (base/'backend.json').write_text(json.dumps(config,indent=2)+'\n')
    for path in (base/'config-home/container/config.toml',base/'state/config/config.toml'):
        path.chmod(0o644)
        path.write_text('[vminit]\nimage = '+json.dumps(config['init_image'])+'\n')
        path.chmod(0o444)
    # Any rebuild revokes earlier qualification, even when only metadata changed.
    Path(config['certificate']).unlink(missing_ok=True)
    report['config']=config
    report['kernel_bytes']=(base/'kernel').stat().st_size
    report['kernel_sha256']=file_hash(base/'kernel')
    report['runtime_version']=runtime_command(config,['--version']).strip()
    (ROOT/'artifacts/day4b1/implementation/installation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

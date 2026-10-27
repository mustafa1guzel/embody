"""Operator-only, byte-accounted official downloads. Never starts candidate code."""
import hashlib
import fcntl
import io
import json
import os
from pathlib import Path
import ssl
import sys
import tarfile
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/day4b1/implementation'
CACHE = ROOT / '.runtime/day4b1/downloads'
LEDGER = OUT / 'downloads.json'
BUDGET = 1_500_000_000
CTX = ssl.create_default_context(cafile='/etc/ssl/cert.pem')

def ledger():
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else {
        'budget_bytes': BUDGET, 'unmetered_documentation_reserve_bytes': 10_000_000,
        'scope': 'HTTP response bodies; reserve covers earlier documentation/metadata. No automatic runtime pulls permitted.',
        'entries': []}

def save(data):
    OUT.mkdir(parents=True, exist_ok=True)
    temporary=LEDGER.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(LEDGER)

def get(url, *, headers=None, maximum=2_000_000, destination=None, expected=None, method='GET'):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/'download.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _get(url,headers=headers,maximum=maximum,destination=destination,expected=expected,method=method)

def _get(url, *, headers, maximum, destination, expected, method):
    data = ledger()
    used = sum(e['received_bytes'] for e in data['entries'])
    if used + maximum + 1 + data['unmetered_documentation_reserve_bytes'] > BUDGET:
        raise RuntimeError('Aggregate download budget would be exceeded')
    entry = {'url': url.split('?')[0], 'method': method, 'received_bytes': 0, 'status': 'STARTED'}
    data['entries'].append(entry)
    save(data)
    req = urllib.request.Request(url, headers={'User-Agent': 'EMBODY-Day4B1', **(headers or {})}, method=method)
    buffer = io.BytesIO() if destination is None else None
    if destination is not None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
    handle = buffer if buffer is not None else destination.open('wb')
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as response:
            while chunk := response.read(min(1024 * 1024, maximum - entry['received_bytes'] + 1)):
                entry['received_bytes'] += len(chunk)
                digest.update(chunk)
                if entry['received_bytes'] > maximum:
                    raise RuntimeError('Response exceeded declared download bound')
                handle.write(chunk)
                save(data)
        entry['sha256'] = digest.hexdigest()
        if expected and entry['sha256'] != expected.removeprefix('sha256:'):
            raise RuntimeError('Downloaded payload digest mismatch')
        entry['status'] = 'VERIFIED' if expected else 'METADATA'
        save(data)
        return buffer.getvalue() if buffer is not None else destination
    except Exception as exc:
        entry['status'] = 'FAILED'
        entry['error'] = type(exc).__name__
        save(data)
        raise
    finally:
        if buffer is None:
            handle.close()

def json_get(url, **kwargs):
    return json.loads(get(url, **kwargs))

def cached(path, expected):
    if not path.is_file(): return False
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1048576):sha.update(chunk)
    return sha.hexdigest()==expected.removeprefix('sha256:')

ACCEPT = ', '.join(('application/vnd.oci.image.index.v1+json', 'application/vnd.oci.image.manifest.v1+json',
                     'application/vnd.docker.distribution.manifest.list.v2+json', 'application/vnd.docker.distribution.manifest.v2+json'))

def registry(host, repo, reference):
    if host == 'ghcr.io':
        token = json_get(f'https://ghcr.io/token?service=ghcr.io&scope=repository:{repo}:pull')['token']
    else:
        token = json_get(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull')['token']
    headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT}
    raw = get(f'https://{host}/v2/{repo}/manifests/{reference}', headers=headers)
    index_digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw)
    if 'manifests' in doc:
        arm = next(m for m in doc['manifests'] if m.get('platform', {}).get('architecture') == 'arm64'
                   and m['platform'].get('os') == 'linux')
        raw = get(f'https://{host}/v2/{repo}/manifests/' + arm['digest'], headers=headers, expected=arm['digest'])
        doc = json.loads(raw)
    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
    return {'host': host, 'repository': repo, 'reference': reference, 'index_digest': index_digest,
            'manifest_digest': digest, 'manifest': doc, 'manifest_text': raw.decode()}, headers

def plan():
    pre = json.loads((ROOT/'artifacts/day4b1/installation_precheck/precheck.json').read_text())
    images = []
    for host, repo, tag in [('ghcr.io','apple/containerization/vminit','0.52.1'),
                             ('registry-1.docker.io','library/python','3.12.15-slim-bookworm')]:
        item, _ = registry(host,repo,tag)
        images.append(item)
    versions = {'mujoco':'3.16.0','numpy':'2.5.4','absl-py':'2.5.1','etils':'1.14.0',
                'glfw':'2.11.0','PyOpenGL':'3.1.10','websockets':'17.3','fsspec':'2026.9.0',
                'typing_extensions':'4.16.0','zipp':'4.1.1'}
    wheels = []
    for name, version in versions.items():
        meta = json_get(f'https://pypi.org/pypi/{name}/{version}/json')
        compatible = [f for f in meta['urls'] if f['filename'].endswith('.whl') and
                      (f['filename'].endswith('py3-none-any.whl') or
                       (('cp312-cp312' in f['filename'] or 'py2.py3-none' in f['filename']) and
                        ('manylinux' in f['filename'] and 'aarch64' in f['filename'] or f['filename'].endswith('none-any.whl'))))]
        if not compatible:
            raise RuntimeError(f'No compatible wheel: {name}=={version}')
        item = min(compatible, key=lambda f:f['size'])
        wheels.append({'name': name,'version':version,'filename':item['filename'],'url':item['url'],
                       'bytes':item['size'],'sha256':item['digests']['sha256']})
    result = {'runtime':pre['signed_installer'],'kernel':pre['default_kernel_archive'],
              'kernel_member':pre['default_kernel_member'],'images':images,'wheels':wheels,
              'native_dependency_reserve_bytes': 25_000_000,
              'note': 'Minimal OCI archive will be assembled locally; no BuildKit, compilers, Xcode or builder images.'}
    result['expected_payload_bytes'] = sum(result[k]['bytes'] for k in ('runtime','kernel')) + sum(w['bytes'] for w in wheels) + sum(
        x['size'] for im in images for x in [im['manifest']['config'],*im['manifest']['layers']])
    assert result['expected_payload_bytes'] + 35_000_000 < BUDGET
    (OUT/'download_plan.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'expected_payload_bytes':result['expected_payload_bytes'],
                      'image_bytes':[(i['repository'],sum(x['size'] for x in [i['manifest']['config'],*i['manifest']['layers']])) for i in images],
                      'wheels_bytes':sum(w['bytes'] for w in wheels)},indent=2))

def fetch_assets():
    plan = json.loads((OUT/'download_plan.json').read_text())
    for kind in ('runtime','kernel'):
        item=plan[kind]
        dest=CACHE/item['name']
        if cached(dest,item['published_sha256']):
            print('Using verified existing',dest.name,flush=True)
            continue
        print('Downloading',item['name'],item['bytes'],flush=True)
        get(item['download_url'],maximum=item['bytes'],destination=dest,expected=item['published_sha256'])
    for wheel in plan['wheels']:
        dest=CACHE/wheel['filename']
        if not cached(dest,wheel['sha256']):
            get(wheel['url'],maximum=wheel['bytes'],destination=dest,expected=wheel['sha256'])
    for image in plan['images']:
        _,headers=registry(image['host'],image['repository'],image['manifest_digest'])
        for blob in [image['manifest']['config'],*image['manifest']['layers']]:
            dest=CACHE/'blobs'/blob['digest'].split(':')[1]
            if not cached(dest,blob['digest']):
                print('Downloading blob',image['repository'],blob['size'],flush=True)
                get(f"https://{image['host']}/v2/{image['repository']}/blobs/{blob['digest']}",
                    headers=headers,maximum=blob['size'],destination=dest,expected=blob['digest'])
    data=ledger()
    print('Total tracked response bytes:',sum(e['received_bytes'] for e in data['entries']),flush=True)

if __name__=='__main__':
    {'plan':plan,'fetch':fetch_assets}[sys.argv[1]]()

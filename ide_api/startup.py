"""Read-only local production preflight. No installs, clients, VMs or simulation."""
from importlib import import_module, metadata
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]

def check(root=ROOT):
    root=Path(root)
    if sys.version_info[:2]!=(3,12):raise ValueError('Use the supported Python 3.12 environment: .venv/bin/python -m ide_api.server')
    dependencies={}
    for package,expected in [('mujoco','3.16.0'),('jsonschema','4.26.0'),('numpy',None),('Pillow',None)]:
        try:
            version=metadata.version(package);import_module('PIL' if package=='Pillow' else package)
        except (ImportError,metadata.PackageNotFoundError,OSError,RuntimeError) as exc:
            raise ValueError(f'Missing or unusable {package}. Restore the reviewed existing environment; nothing was installed.') from exc
        if expected and version!=expected:raise ValueError(f'{package} {expected} required; found {version}. Review the environment; no automatic update.')
        numbers=tuple(int(n) for n in re.match(r'^(\d+)\.(\d+)',version).groups())
        if package=='numpy' and numbers<(2,3) or package=='Pillow' and numbers<(10,0):raise ValueError(f'{package} {version} is below the declared supported minimum. Review the existing environment.')
        dependencies[package]=version
    try:
        base=root/'frontend/dist'
        if base.is_symlink() or (base/'index.html').is_symlink():raise ValueError('Symlink build rejected')
        raw=(base/'index.html').read_text()
        assets=re.findall(r'(?:src|href)="(/assets/[^"?#]+)"',raw)
        if not assets:raise ValueError('No production asset references')
        for asset in assets:
            relative=Path(asset.lstrip('/'))
            if '..' in relative.parts:raise ValueError('Invalid production asset reference')
            target=base/relative
            if not target.is_file() or any(p.is_symlink() for p in [target,*target.parents]):raise ValueError('Missing or symlinked asset')
            with target.open('rb') as stream:stream.read(1)
    except (ValueError,OSError,UnicodeError) as exc:
        raise ValueError('Production build missing or incomplete. With reviewed frontend dependencies installed, run: cd frontend && npm run build') from exc
    return {'status':'READY','application':'EMBODY','python':sys.version.split()[0],
        'dependencies':dependencies,'frontend':'LOCAL_PRODUCTION_BUILD','model_requests':0,'native_runs':0}

"""World envelope and immutable safe storage, reusing the audited local store."""
import json,os
from pathlib import Path
from physics.contracts import canonical
from workspace.data import decode_json
from .schema import validate,identity


def envelope(world):return {'schema_version':1,'sha256':identity(world),'world':validate(world)}
def load(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=120000:raise ValueError('Bounded world import required')
    v=decode_json(raw)
    if not isinstance(v,dict) or set(v)!={'schema_version','sha256','world'} or type(v['schema_version']) is not int or v['schema_version']!=1:raise ValueError('Invalid world envelope')
    w=validate(v['world'])
    if identity(w)!=v['sha256']:raise ValueError('World identity mismatch')
    return w


class Store:
    def __init__(self,root):
        self.root=Path(root)
        if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('Symlink world root rejected')
        self.root.mkdir(parents=True,exist_ok=True)
    def save(self,w):
        w=validate(w);key=identity(w);path=self.root/(key+'.json');raw=(canonical(envelope(w))+'\n').encode()
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if self.get(key)!=w:raise ValueError('World storage identity collision')
        else:
            with os.fdopen(fd,'wb') as f:f.write(raw)
        return key
    def get(self,key):
        if not isinstance(key,str) or len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Invalid world key')
        fd=os.open(self.root/(key+'.json'),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:w=load(f.read(120001))
        if identity(w)!=key:raise ValueError('World key mismatch')
        return w

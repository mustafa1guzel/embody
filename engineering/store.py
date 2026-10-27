"""Content-addressed immutable JSON, O_NOFOLLOW and exact bounded identities."""
import os,json
from pathlib import Path
from physics.contracts import canonical,digest
from workspace.data import decode_json

class Store:
    def __init__(self,root):
        self.root=Path(root)
        if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('Symlink engineering root rejected')
        self.root.mkdir(parents=True,exist_ok=True)
    def put(self,value):
        key=digest(value);path=self.root/(key+'.json');raw=(canonical(value)+'\n').encode()
        if len(raw)>20000000:raise ValueError('Stored artifact exceeds limit')
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if digest(self.get(key))!=key:raise ValueError('Artifact collision')
        else:
            with os.fdopen(fd,'wb') as f:f.write(raw)
        return key
    def get(self,key):
        if not isinstance(key,str) or len(key)!=64 or any(x not in '0123456789abcdef' for x in key):raise ValueError('Invalid immutable identity')
        fd=os.open(self.root/(key+'.json'),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:raw=f.read(20000001)
        if len(raw)>20000000:raise ValueError('Artifact too large')
        value=decode_json(raw)
        if digest(value)!=key:raise ValueError('Stored identity mismatch')
        return value

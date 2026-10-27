"""Canonical identity-checked data import and append-only local revision store."""
import json
import os
from pathlib import Path
from physics.contracts import canonical
from workspace.data import decode_json
from .assemblies import validate, identity, identifier

MAX_BYTES=120_000


def export(a):return {'schema_version':1,'sha256':identity(a),'assembly':validate(a)}


def load(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:raise ValueError('Assembly import exceeds byte limit')
    data=decode_json(raw)
    if not isinstance(data,dict) or set(data)!={'schema_version','sha256','assembly'} or data['schema_version']!=1:raise ValueError('Invalid assembly envelope')
    a=validate(data['assembly'])
    if identity(a)!=data['sha256']:raise ValueError('Assembly hash mismatch')
    return a


class Store:
    def __init__(self, root):
        self.root=Path(root)
        # No root/path component may be an attacker-controlled symlink.
        if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('Symlink store root rejected')
        self.root.mkdir(parents=True,exist_ok=True)

    def save(self,a):
        a=validate(a);key=identity(a);raw=(canonical(export(a))+'\n').encode()
        if len(raw)>MAX_BYTES:raise ValueError('Assembly exceeds byte limit')
        path=self.root/(key+'.json')
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if self.get(key)!=a:raise ValueError('Saved identity collision')
        else:
            with os.fdopen(fd,'wb') as f:f.write(raw)
        return {'key':key,'assembly':a}

    def get(self,key):
        if not isinstance(key,str) or len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Invalid saved assembly identity')
        fd=os.open(self.root/(key+'.json'),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:raw=f.read(MAX_BYTES+1)
        a=load(raw)
        if identity(a)!=key:raise ValueError('Stored file identity mismatch')
        return a

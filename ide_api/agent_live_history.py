"""Operator-only recovery of existing cost history. No keys or provider requests.

Uses the exact prior approved anchor, not an empty replacement financial ledger.
The history root is private local configuration, never HTTP/model data.
"""
from itertools import islice
from pathlib import Path
import hashlib
from core.simulation import ROOT
from core.agent.development_budget import historical_accounting
from ide_api.rail_sweeps import digest
from workspace.data import bounded_read,decode_json
ANCHOR='artifacts/phase18e_6/20261026/live_consent_request.json'
ANCHOR_SHA='fe2eadc44fce0f4fec101e1827a70a3ffab58eb1932a1b5f948173f908dd60ae'
OWN='artifacts/phase18e_6/20261026/live_execution/api_cost_ledger.json'

def leaf_paths(root):
 folder=Path(root)/'execution'
 if not folder.exists():return []
 if any(p.is_symlink() for p in (folder,*folder.parents)):raise ValueError('Symlink accounting namespace refused')
 dirs=list(islice(folder.iterdir(),129))
 if len(dirs)>128:raise ValueError('Accounting namespace retention bound exceeded')
 out=[]
 for p in sorted(dirs):
  if p.is_symlink():raise ValueError('Symlink session refused')
  if (p/'api_cost_ledger.json').exists():out.append(p/'api_cost_ledger.json')
 return out

def recover(root):
 root=Path(root)
 if not root.is_absolute() or any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Operator must select the actual nonsymlink history root')
 value=decode_json(bounded_read(root,ANCHOR))
 if value.get('sha256')!=ANCHOR_SHA or digest(value['definition'])!=ANCHOR_SHA:raise ValueError('Existing approved accounting anchor differs')
 manifest=value['definition']['historical_api_ledgers'];paths=[]
 if len(manifest)!=18:raise ValueError('Unexpected original accounting anchor')
 for name,h in manifest.items():
  raw=bounded_read(root,name)
  if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Original leaf ledger hash differs')
  paths.append(root/name)
 paths.append(root/OWN)
 paths+=leaf_paths(root/'artifacts/phase19c/workspace_requests')
 history=historical_accounting(paths)
 return {'anchor_canonical_sha256':ANCHOR_SHA,'history_root':str(root),'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'accounted_cost_usd':history['accounted_cost_usd'],'measured_cost_usd':history['measured_cost_usd'],'leaf_count':len(paths)}

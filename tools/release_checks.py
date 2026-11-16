"""Read-only targeted release checks; never installs, executes physics or rewrites baselines."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git_binary():
 from ide_api.research.bundles import repo_base
 import shutil
 p=Path('/Applications/GitHub Desktop.app/Contents/Resources/app/git/bin/git')
 v=str(p) if p.is_file() else shutil.which('git')
 if not v:raise ValueError('Working existing Git required')
 return v

def checks(original_root=None,original_inventory=None):
 git=git_binary();base=subprocess.check_output([git,'rev-parse','HEAD'],cwd=ROOT,text=True).strip();paths=subprocess.check_output([git,'ls-files','--cached','--others','--exclude-standard'],cwd=ROOT).decode().splitlines();protected=list((ROOT/'core').rglob('*.py'))+list((ROOT/'configs').glob('*.json'))+[ROOT/'robot'/p for p in ('controller.py','rail_carriage.xml','arm_controller.py','planar_arm.xml')]+list((ROOT/'physics').glob('*.py'))+[ROOT/'workspace/workflow.py',ROOT/'workspace/data.py'];mismatch=[]
 tracked=subprocess.check_output([git,'ls-tree','-r','--name-only','HEAD'],cwd=ROOT,text=True).splitlines();fixtures=[p for p in tracked if p.startswith(('examples/','artifacts/','frontend/test/'))]
 for p in [*protected,*[ROOT/f for f in fixtures]]:
  name=str(p.relative_to(ROOT));expected=hashlib.sha256(subprocess.check_output([git,'show','HEAD:'+name],cwd=ROOT)).hexdigest()
  if sha(p)!=expected:mismatch.append(name)
 # Only exact proposed changes are scanned; existing private-free historical fixtures are pinned above.
 changed=set(subprocess.check_output([git,'diff','--name-only'],cwd=ROOT,text=True).splitlines())|set(subprocess.check_output([git,'ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines());privacy=[];links=[]
 for name in sorted(changed):
  p=ROOT/name
  if p.suffix=='.png':continue
  raw=p.read_text()
  for i,line in enumerate(raw.splitlines(),1):
   if re.search(r'/Users/(?!example/)[A-Za-z0-9_.-]+/|/private/(?:tmp|var)/[A-Za-z0-9_.-]+|/home/[A-Za-z0-9_.-]+/|sk-(?:proj-)?[A-Za-z0-9_-]{16,}|-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}',line):privacy.append({'path':name,'line':i})
  if p.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',raw):
    if '://' not in target and not target.startswith('#') and not (p.parent/target.split('#')[0]).exists():links.append({'path':name,'target':target})
 whitespace=subprocess.run([git,'diff','--check'],cwd=ROOT,capture_output=True,text=True)
 original={'status':'NOT_REQUESTED','checked':0,'heads':0,'mismatches':[]}
 if original_root is not None and original_inventory is not None:
  inv=json.loads(Path(original_inventory).read_text())['files'];root=Path(original_root);bad=[n for n,h in inv.items() if not (root/n).is_file() or sha(root/n)!=h];original={'status':'PASS' if not bad else 'FAIL','checked':len(inv),'heads':sum(n.endswith('/head.json') for n in inv),'mismatches':bad}
 return {'status':'PASS' if not mismatch and not privacy and not links and whitespace.returncode==0 and original['status']!='FAIL' else 'FAIL','base':base,'protected_count':len(protected),'fixture_count':len(fixtures),'protected_or_fixture_mismatches':mismatch,'privacy_findings':privacy,'broken_links':links,'whitespace_exit':whitespace.returncode,'original_scope':original,'qualification':'No certificate validity or refresh claimed; compared to existing committed source only.'}

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--original-root');parser.add_argument('--original-inventory');args=parser.parse_args();result=checks(args.original_root,args.original_inventory);print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='PASS' else 1)

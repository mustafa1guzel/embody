"""Read-only baseline review/proposal builder. No runtime or qualification calls."""
from pathlib import Path
import ast,copy,difflib,json,time
from importlib.metadata import version
from physics.contracts import digest
from robustness.contracts import file_hash,write_once
ROOT=Path(__file__).resolve().parents[1]
OLD_REQ='4bdc1ab8bcd6c287b4e0e4f73c6be2b38127a0f75ba49da858fadb1bc3201f5f'
NEW_REQ='b90007317a9e384967c9a9e7c891795deeee4bcaa3b26c6514bac071fe281fcb'

def validate_migration(original,proposed):
 if set(original)!=set(proposed):raise ValueError('Protected path set must be identical')
 delta=[n for n in original if original[n]!=proposed[n]]
 if delta!=['requirements.txt'] or original['requirements.txt']!=OLD_REQ or proposed['requirements.txt']!=NEW_REQ:raise ValueError('Only exact historically documented requirements delta allowed')
 return {'status':'EXACT_ONE_FILE_MIGRATION','delta':delta,'protected_paths':len(original)}

def prepare(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 baseline=ROOT/'artifacts/day4b1/implementation/before.json';original=json.loads(baseline.read_text());candidate=copy.deepcopy(original);candidate['requirements.txt']=NEW_REQ;validation=validate_migration(original,candidate)
 historical=ROOT/'artifacts/day11_12/20261024_live_agent_repair/before_sources/requirements.txt'
 # The verified historical provenance report names the exact original source.
 history=json.loads((ROOT/'artifacts/phase17_2/20261025/requirements_history_analysis.json').read_text())
 assert history['before_plus_exact_added_line_equals_current_bytes'] and file_hash(ROOT/'requirements.txt')==NEW_REQ
 config=json.loads((ROOT/'.runtime/day4b1/backend.json').read_text());certificate=Path(config['certificate']);cert=json.loads(certificate.read_text())
 core=ROOT/'core/day4b1.py';source=core.read_text();tree=ast.parse(source)
 function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='original_project_intact')
 authorized=next(n.value for n in ast.walk(function) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='authorized' for t in n.targets));authorized=ast.literal_eval(authorized)
 mismatches=[{'path':n,'expected':h,'actual':file_hash(ROOT/n) if (ROOT/n).is_file() else None} for n,h in original.items() if n not in authorized and Path(n).name!='.DS_Store' and (not (ROOT/n).is_file() or file_hash(ROOT/n)!=h)]
 assert [r['path'] for r in mismatches]==['requirements.txt']
 payload={'version':2,'predecessor_inventory_sha256':file_hash(baseline),'files':candidate,'delta':{'requirements.txt':{'before':OLD_REQ,'after':NEW_REQ,'reason':'Previously installed jsonschema==4.26.0 explicitly declared during Day11/12; no new installation'}},'historical_provenance':history}
 write_once(out/'protected_baseline_v2.json',payload);v2hash=file_hash(out/'protected_baseline_v2.json')
 # A review artifact only: this exact proposed code is NOT installed/imported.
 loader=f'''def reviewed_protected_inventory():
    # Explicit version2 selection after separate human migration approval.
    old_path=OUTPUT/'before.json'
    v2_path=ROOT/{str((out/'protected_baseline_v2.json').relative_to(ROOT))!r}
    if file_hash(old_path)!={file_hash(baseline)!r} or file_hash(v2_path)!={v2hash!r}:
        raise IsolationBlocked('Versioned protected baseline identity differs')
    old=json.loads(old_path.read_text());data=json.loads(v2_path.read_text());new=data['files']
    if set(new)!=set(old) or [n for n in old if old[n]!=new[n]]!=['requirements.txt']:
        raise IsolationBlocked('Unapproved protected baseline delta')
    if old['requirements.txt']!={OLD_REQ!r} or new['requirements.txt']!={NEW_REQ!r}:
        raise IsolationBlocked('Requirements migration differs')
    return new

'''
 new_source=source.replace('def original_project_intact():',loader+'def original_project_intact():').replace("baseline=json.loads((OUTPUT/'before.json').read_text())","baseline=reviewed_protected_inventory()")
 assert new_source!=source
 with (out/'proposed_core_day4b1.py').open('x') as f:f.write(new_source)
 patch=''.join(difflib.unified_diff(source.splitlines(True),new_source.splitlines(True),fromfile='core/day4b1.py',tofile='core/day4b1.py'))
 with (out/'protected_baseline_migration.patch').open('x') as f:f.write(patch)
 d={'mission':'Phase18E.2 protected-baseline migration ONLY; UNAPPLIED','version':2,'predecessor_inventory_sha256':file_hash(baseline),'candidate_baseline_file_sha256':v2hash,'current_core_sha256':file_hash(core),'proposed_core_sha256':file_hash(out/'proposed_core_day4b1.py'),'patch_sha256':file_hash(out/'protected_baseline_migration.patch'),'allowed_delta':payload['delta'],'protected_paths':len(original),'unchanged_allowlist':sorted(authorized),'allowed_effects':['Only after fresh explicit migration approval: apply exact reviewed baseline loader patch and select immutable version2 manifest','Retain original before.json, certificate bytes and all historical evidence; no silent rebaseline','Record approval and source hashes separately'],'vm_launches':0,'installations':0,'qualification_authority':False,'status':'PENDING_SEPARATE_APPROVAL','prerequisites':['Current full protected inventory differs only by exact declared requirements delta','Independent review of patch and all338 entries; changing any other hash requires new approval','Changed trusted core identity invalidates old certificate; candidate execution must stay blocked until fresh qualification']}
 write_once(out/'baseline_migration_consent.json',{'definition':d,'sha256':digest(d),'authorization':'NOT_GRANTED'})
 probe_order=['inventory','filesystem','network','scratch','memory','memory_group','processes','files','invalid','oversized','timeout','descendant','cpu','one_vm_lock_outer','trusted_baseline_A','trusted_baseline_B','trusted_baseline_C']
 assertions=sorted({n.slice.value for n in ast.walk(tree) if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Name) and n.value.id=='checks' and isinstance(n.slice,ast.Constant) and isinstance(n.slice.value,str)})
 q={'mission':'Phase18E.2 fresh containment qualification ONLY; NOT_EXECUTED','max_serial_vm_launch_attempts':17,'probe_order':probe_order,'execution_window_seconds':1200,'retries':0,'network':'none; no DNS; no auto-pulls or downloads','vm_configuration':{'cpus':1,'memory':'1g','uid':'65532:65532','read_only_root':True,'host_mounts':False,'capabilities':'ALL dropped','tmpfs':'32m,nosuid,nodev,noexec','shm':'8m','nproc':16,'nofile':64,'core_bytes':0,'file_bytes':33554432,'address_space_bytes':805306368,'default_vm_wall_seconds':60,'default_cpu_seconds':30,'probe_overrides':{'ordinary_named_probes_wall_seconds':15,'memory_group_wall_seconds':20,'timeout_and_descendant_wall_seconds':3,'cpu_wall_seconds':12,'cpu_cpu_seconds':2}},'nested_lock_probe':'Image metadata inspected then lock acquisition fails BEFORE runtime run; zero additional VM launch','acceptance':{'existing_qualify_assertions':assertions,'must_pass_all_existing_checks':True,'certificate_validity_seconds':86400,'trusted_parity':{'families':['original rail scenarios A,B,C'],'state_action_samples_per_scenario':5,'maximum_command_difference':1e-12},'cleanup':'Each named VM killed/deleted and absence independently checked; final dedicated inventory empty; inability revokes qualification'},'dependencies':{'versions':{n:version(n) for n in ('mujoco','numpy','jsonschema')},'config_sha256':file_hash(ROOT/'.runtime/day4b1/backend.json'),'config':config,'old_certificate_sha256':file_hash(certificate),'kernel_sha256':file_hash(Path(config['kernel'])),'runtime_binary_sha256':file_hash(Path(config['runtime']))},'prerequisites':['Separate exact baseline migration approval and implementation completed','Current core/day4b1.py matches proposed_core_sha256 from separately approved migration','All other current trusted source/runtime/kernel/image identities frozen at authorization; fail if any differ','Signed runtime1.6.0 and both pinned images already local; no installation/download authority','Empty dedicated inventory; dummy canary path absent; preserve previous certificate and historical outputs before any certificate removal'],'allowed_effects':['Archive existing expired certificate before unchanged qualify removes it','Use new write-once output directory; never overwrite old containment.json/history','Start/stop installed local runtime API only as required and restore its prior state','Create/remove exclusive dummy /private/tmp/embody-host-canary; pass dummy environment canaries, never real secrets','Run17 developer containment probes/trusted original rail baseline sessions; save genuine outcomes','Write new certificate only if every original assertion passes; failure keeps execution blocked'],'prohibited':['No paid calls','No model source/controller patch or installation','No security assertion weakening/time changes/blanket baseline exception','No candidate evaluate command or additional VM pytest batch'],'migration_manifest_sha256':digest(d),'status':'BLOCKED_PRECONDITION_PENDING_MIGRATION_AND_FRESH_QUALIFICATION_APPROVAL','current_core_qualify_sha256':file_hash(core),'expected_after_migration_core_sha256':d['proposed_core_sha256']}
 write_once(out/'vm_qualification_consent.json',{'definition':q,'sha256':digest(q),'authorization':'NOT_GRANTED'})
 write_once(out/'audit.json',{'status':'READ_ONLY_PREPARATION_COMPLETE','baseline_validation':validation,'current_protected_mismatches':mismatches,'old_certificate_status':cert['status'],'certificate_age_seconds':time.time()-cert['created_unix'],'certificate_currently_valid':False,'historical_requirements_analysis':history,'actual_core_unchanged':file_hash(core)==d['current_core_sha256'],'baseline_applied':False,'vm_launches':0,'qualification_checks_in_saved_certificate':len(cert['checks']),'new_api_cost_usd':'0'})
 return {'migration_manifest_sha256':digest(d),'vm_qualification_manifest_sha256':digest(q),'status':'PROPOSED_NOT_APPLIED','vm_launches':0}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(prepare(a.output.resolve()),indent=2))

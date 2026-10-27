"""Freeze reviewable source bytes, matrix, native model/contract hashes before VM work."""
from pathlib import Path
import hashlib
from core.simulation import ROOT
from core.agent.patching import CandidateStore
from physics.contracts import canonical,digest
from .contracts import Experiment,frozen_sources,implementation_identity,write_once
from .sampling import sample,SEEDS
from .parameters import schema
from .perturbation import compile_scenario,contract_dict


def freeze(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);sources=frozen_sources();matrix=[]
    for family in ('rail','arm'):
        original=(ROOT/sources[family]['baseline']['path']).read_bytes()
        folder=output/'controllers';folder.mkdir(exist_ok=True)
        (folder/(family+'_baseline.py')).write_bytes(original)
        raw=sources[family]['repair'].pop('source');(folder/(family+'_repair.py')).write_text(raw)
        validation=CandidateStore(ROOT,output/'validation'/family,target=sources[family]['baseline']['path']).propose(
            target_path=sources[family]['baseline']['path'],expected_original_sha256=sources[family]['baseline']['sha256'],
            proposed_source=raw,explanation='Exact frozen historical GPT proposal; no new inference or source modification')
        if validation['validation_status']!='VALID':raise ValueError('Historical source no longer meets the current source policy')
        sources[family]['repair']['validation']={k:v for k,v in validation.items() if k!='candidate_id'}
        for row in sample(family):
            plant=compile_scenario(row,sources[family]['repair']['sha256']);c=plant['contract']
            model_path=output/'models'/(row['id']+'.xml');model_path.parent.mkdir(exist_ok=True);model_path.write_text(plant['xml'])
            write_once(output/'contracts'/(row['id']+'.json'),{'contract':contract_dict(c),'guard':plant['guard']})
            matrix.append({**row,'model_sha256':hashlib.sha256(plant['xml'].encode()).hexdigest(),
                           'physics_contract_sha256':c.identity,'guard':plant['guard']})
    definition={'schema_version':1,'families':['rail','arm'],'sources':sources,'implementation':implementation_identity(),
        'parameters':schema(),'matrix':matrix,'seeds':SEEDS,'sampling':'1 nominal anchor + 15 nominal IID uniform + 16 wider IID uniform + 8 deliberate boundary cases, per family',
        'endpoint_convention':'Random [low,high); explicit boundary rows include endpoints. No outcome-dependent resampling.',
        'acceptance':{'rail':'Unchanged core.diagnostics.evaluate_safety: 3 s/.005 s, no contact, >=.05 m, final abs(v)<.03 m/s.',
                      'arm':'Unchanged core.robots.execution.acceptance and configs/arm_tasks.json requirements.'},
        'search':{'additional_evaluations_per_family':6,'seed':1000003,'local_range_fraction':.1,
                  'minimization_trials_per_family':6,'confirmation_evaluations_per_family':1,'numerical_ce_band':1e-8,
                  'objective':'Measured normalized requirement excess; greedy sparsity then normalized L1 simplification, no monotonicity.'},
        'latency':{'status':'NOT_IMPLEMENTED','delay_s':0.},'numerical_sensitivity':{'status':'NOT_IMPLEMENTED','timesteps_fixed':True},
        'api_calls_allowed':0,'candidate_execution':'Qualified AppleVMBackend only; first rollout + fresh independent closed-loop VM per case.',
        'authorization':'Fresh explicit approval of this experiment SHA-256 required; never inherited from Day 9.',
        'resource_limits':{'maximum_candidate_evaluations':sum(r['guard']['status']!='PROVEN_INFEASIBLE' for r in matrix)+26,
                           'maximum_candidate_vm_sessions':2*(sum(r['guard']['status']!='PROVEN_INFEASIBLE' for r in matrix)+26),
                           'representative_probe_vm_sessions':4,'vm_wall_deadline_s':60,'vm_cpu_deadline_s':30,
                           'one_vm_at_a_time':True,'cgroup_memory_bytes':1073741824,'scratch_bytes':33554432,
                           'batch_wall_deadline_s':3600},
        'unsupported':['No real-world failure probability or universal safety proof.','No new LLM repair-generation ablation.','No controller installation.'],
        'evidence_state':'FROZEN_OFFLINE; new robustness dynamics not yet executed'}
    e=Experiment(canonical(definition));write_once(output/'experiment.json',{'sha256':e.identity,'definition':definition})
    write_once(output/'approval_request.json',approval_report(e))
    return e


def approval_report(e):
    d=e.data;eligible=sum(r['guard']['status']!='PROVEN_INFEASIBLE' for r in d['matrix'])
    return {'experiment_sha256':e.identity,'sources':{f:{v:s['sha256'] for v,s in sources.items()} for f,sources in d['sources'].items()},
        'frozen_parameter_rows':len(d['matrix']),'eligible_paired_cases':eligible,
        'benchmark_original_trusted_host_rollouts':eligible*2,'benchmark_repair_vm_sessions':eligible*2,
        'maximum_additional_search_minimize_confirm_vm_sessions':52,'representative_developer_probe_vm_sessions':4,
        'existing_containment':'Use current source-bound qualification; if stale, repeat existing developer-only containment probes first.',
        'runtime_limits':d['resource_limits'],'accessed_data':'Frozen controller strings, bounded trusted model XML and numeric MuJoCo integration state only; no private host mounts or credentials.',
        'api_requests':0,'installation':False,'network_access':False,
        'execution_method':d['candidate_execution'],'adaptive_scope':d['search'],'required_approval':'Explicit user approval of this exact manifest and bounded batch'}

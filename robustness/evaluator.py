"""Actual trusted dynamics; frozen GPT strings go only through AppleVMBackend."""
from pathlib import Path
import hashlib
import time
import numpy as np
from core.simulation import ROOT,run_simulation,write_json
from core.agent.patching import source_errors
from core.agent.vm_backend import IsolationBlocked
from core.agent.candidate_execution import verify_fresh
from core.diagnostics import independently_verify_safety,evaluate_safety
from core.robots.execution import first_run,independent,save,acceptance
from physics.profiler import profile as rail_profile
from physics.guard import assess_task
from .contracts import write_once,file_hash
from .perturbation import compile_scenario
from .classification import classify,violations,objective
from .qualification import require
from workspace.data import bounded_read


def _metrics(plant,samples,accepted):
    c=plant['contract'];family=plant['scenario']['family']
    if family=='rail':
        gap=min(s['wall_clearance'] for s in samples);speed=abs(samples[-1]['velocity'])
        onset=next((s for s in samples if s['velocity']>0 and s['generalized_actuator_force']<0),None)
        margins={'clearance_m':gap-c.minimum_clearance_m+1e-12,'final_speed_mps':c.final_speed_tolerance_mps-speed,
                 'contacts':-float(accepted['wall_collision_events'])}
        measured={'minimum_clearance_m':gap,'final_velocity_mps':samples[-1]['velocity'],'braking_onset':onset,
                  'available_deceleration_mps2':c.braking_force_n/c.generalized_inertia_kg,
                  'onset_analytical_assessment':assess_task(c,velocity_mps=onset['velocity'],clearance_m=onset['wall_clearance'],
                      remaining_time_s=max(0.,c.deadline_s-onset['time']),contact_present=onset['wall_collision']) if onset else None,
                  'profiler':rail_profile(samples,c),'wall_contact_episodes':accepted['wall_collision_events']}
    else:
        window=[s for s in samples if s['time']>=c.duration_s-c.settling_window_s-1e-10]
        margins={'target_error_m':c.target_tolerance_m-samples[-1]['target_error_m'],
                 'final_speed_rad_s':c.final_velocity_limit-max(map(abs,samples[-1]['qvel_rad_s'])),
                 'settling_error_m':c.target_tolerance_m-max(s['target_error_m'] for s in window),
                 'settling_speed_rad_s':c.final_velocity_limit-max(abs(v) for s in window for v in s['qvel_rad_s']),
                 'peak_speed_rad_s':c.maximum_velocity-max(abs(v) for s in samples for v in s['qvel_rad_s']),
                 'joint_limit_rad':min(v for s in samples for v in s['joint_limit_margin_rad'])+c.joint_limit_tolerance,
                 'torque_nm':min(min(abs(j.effort_range[0]),abs(j.effort_range[1]))-abs(s['generalized_torque_nm'][i])+1e-10 for s in samples for i,j in enumerate(c.joints)),
                 'contacts':-float(sum(bool(s['contacts']) for s in samples))}
        from physics.vector_profiler import profile
        settled=len(samples)
        for k in range(len(samples)-1,-1,-1):
            s=samples[k]
            if s['target_error_m']>c.target_tolerance_m or max(map(abs,s['qvel_rad_s']))>=c.final_velocity_limit:break
            settled=k
        measured={'final_error_m':samples[-1]['target_error_m'],'final_joint_velocity_rad_s':samples[-1]['qvel_rad_s'],
                  'settled_from_measured_time_s':samples[settled]['time'] if settled<len(samples) else None,
                  'profiler':profile(samples,c),'last_window_checks':{k:v for k,v in margins.items() if k.startswith('settling')}}
    return margins,measured


def evaluate(experiment,folder,row,variant,output,*,backend=None,proof=None,approved_sha=None):
    """Internal trusted evaluator. The batch owns durable budgets/approval scope."""
    if variant not in ('baseline','repair'):raise ValueError('Unknown frozen source variant')
    experiment.assert_current();folder=Path(folder);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter();family=row['family'];info=experiment.data['sources'][family][variant]
    source=bounded_read(folder,'controllers/'+family+'_'+variant+'.py').decode()
    if hashlib.sha256(source.encode()).hexdigest()!=info['sha256']:raise ValueError('Frozen controller source mismatch')
    plant=compile_scenario(row,info['sha256']);c=plant['contract']
    frozen=next((r for r in experiment.data['matrix'] if r['id']==row['id']),None)
    if frozen is not None and (frozen!=row or frozen['model_sha256']!=hashlib.sha256(plant['xml'].encode()).hexdigest()):
        raise ValueError('Scenario no longer matches frozen matrix')
    result={'family':family,'variant':variant,'scenario':row,'controller_sha256':info['sha256'],
            'model_sha256':hashlib.sha256(plant['xml'].encode()).hexdigest(),'contract_sha256':c.identity,
            'guard':plant['guard'],'execution':'NOT_RUN','independent_verification':'NOT_RUN',
            'physical_safety_status':'NOT_EVALUATED','margins':{},'metrics':{},'acceptance':None,'evidence_directory':str(output)}
    with (output/'effective_model.xml').open('x') as f:f.write(plant['xml'])
    write_once(output/'contract.json',c.to_dict())
    try:
        if variant=='repair':
            require(experiment,backend,proof or {},approved_sha)
            original=(ROOT/experiment.data['sources'][family]['baseline']['path']).read_text()
            if source_errors(original,source):raise ValueError('Frozen candidate fails current source policy')
        if plant['guard']['status']=='PROVEN_INFEASIBLE':
            result.update(classification='TASK_INFEASIBLE',physical_safety_status='NOT_APPLICABLE')
        else:
            if family=='rail':
                if variant=='baseline':
                    from robot.controller import faulty_braking_controller
                    run=run_simulation(bodybase=plant['body'],worldbase=plant['world'],controller=faulty_braking_controller,
                        save_render=False,artifacts_dir=output/'physical')
                    check=independently_verify_safety(run)
                else:
                    with backend.controller(source,plant['xml']) as (remote,exchanges,ready):
                        run=run_simulation(bodybase=plant['body'],worldbase=plant['world'],controller=remote,save_render=False,artifacts_dir=output/'physical')
                    check=verify_fresh(run,backend,source,exchanges)
                    write_once(output/'worker_exchanges.json',{'handshake':ready,'exchanges':exchanges})
                run['metadata']['controller']={'name':'frozen_'+variant,'source_sha256':info['sha256'],'origin':info['origin']}
                write_json(output/'physical/telemetry.json',{'metadata':run['metadata'],'samples':run['telemetry']})
                write_once(output/'independent.json',check);samples=run['telemetry']
                accepted=check['safety_acceptance']
                local=evaluate_safety(samples,plant['world'],plant['model'].geom('wall').id)
                # Independent native distance queries can differ at the final bit.
                # Require identical decisions/criteria/counts; compare measured SI
                # values with the existing 1e-12 verification tolerance.
                numeric=('minimum_measured_clearance_m','final_speed_ms','final_time_s')
                if (any(accepted[k]!=local[k] for k in ('status','criteria','checks','wall_collision_events','wall_contact_samples'))
                        or any(abs(accepted[k]-local[k])>1e-12 for k in numeric)):
                    raise ValueError('Independent rail acceptance differs')
            else:
                f=plant['family']
                if variant=='baseline':
                    run=first_run(f,row['id'],f.baseline(),info['sha256']);check=independent(run,None,None,family=f)
                    exchanges=None
                else:
                    with backend.controller(source,plant['xml']) as (remote,exchanges,ready):run=first_run(f,row['id'],remote,info['sha256'])
                    check=independent(run,source,backend,exchanges)
                save(f,row['id'],run,check,output/'physical',info['origin'],exchanges)
                write_once(output/'independent.json',check);samples=run['samples'];accepted=check['safety_acceptance']
            if family=='rail' and run['metadata']['warnings']:raise ValueError('MuJoCo warning invalidates robustness result')
            if accepted is None or not samples:raise ValueError('No measured acceptance')
            margins,measured=_metrics(plant,samples,accepted)
            result.update(execution='PASS',independent_verification=check['verification_execution'],acceptance=accepted,
                          physical_safety_status=accepted['status'] if check['verification_execution']=='PASS' else 'NOT_EVALUATED',
                          margins=margins,metrics=measured,samples_count=len(samples))
            result['classification']=classify(result['guard'],result['execution'],result['independent_verification'],margins,accepted['status']=='PASS')
    except IsolationBlocked as exc:result.update(execution='BLOCKED',classification='EXECUTION_BLOCKED',reason=str(exc)[:512])
    except (ValueError,RuntimeError,OSError,AssertionError,TimeoutError) as exc:
        result.update(execution='FAIL',physical_safety_status='NOT_EVALUATED',classification='SIMULATION_OR_NUMERICAL_FAILURE',reason=type(exc).__name__+': '+str(exc)[:512])
    result['elapsed_s']=time.perf_counter()-started;result['violations']=violations(result);result['severity']=objective(result)
    result['artifact_sha256']={p.relative_to(output).as_posix():file_hash(p) for p in output.rglob('*') if p.is_file()}
    write_once(output/'result.json',result);return result

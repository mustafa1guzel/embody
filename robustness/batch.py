"""Operator-only bounded batch. No implicit Day 9 permission and no API transport."""
from pathlib import Path
import time
from core.agent.vm_backend import AppleVMBackend,IsolationBlocked
from .contracts import Experiment,write_once
from .qualification import qualify,check_approval
from .evaluator import evaluate
from .counterexamples import search
from .minimization import minimize


def run(folder,*,approved_sha,refresh_containment=False):
    folder=Path(folder);experiment=Experiment.load(folder);check_approval(experiment,approved_sha)
    output=folder/'evaluation';output.mkdir(exist_ok=False);started=time.time()
    write_once(output/'approval.json',{'experiment_sha256':approved_sha,'source':'Explicit operator invocation after user approval of the frozen manifest',
                                     'source_installation_authorized':False,'api_calls_allowed':0,'started_unix':started})
    backend=AppleVMBackend();all_results=[];benchmark=[];searches={};minimized={};counter=0;candidate_calls=0;status='BLOCKED'
    def one(row,variant='repair'):
        nonlocal counter,candidate_calls
        if time.time()-started>3480:raise IsolationBlocked('Batch time budget exhausted; reserve two 60-second VM deadlines before dispatch')
        if variant=='repair':
            if candidate_calls>=experiment.data['resource_limits']['maximum_candidate_evaluations']:raise IsolationBlocked('Candidate evaluation budget exhausted')
            candidate_calls+=1
        identifier=f'{counter:04d}_{row["id"]}_{variant}';counter+=1
        write_once(output/'dispatch'/f'{counter:04d}.json',{'scenario':row,'variant':variant,'candidate_evaluation_index':candidate_calls,'started_unix':time.time()})
        result=evaluate(experiment,folder,row,variant,output/'runs'/identifier,backend=backend,proof=proof,approved_sha=approved_sha)
        all_results.append(result)
        if result['classification']=='EXECUTION_BLOCKED':raise IsolationBlocked(result.get('reason','Execution blocked'))
        return result
    try:
        if refresh_containment:
            from core.day4b1 import qualify as containment
            base=containment(output=output/'containment')
            if base['status']!='PASS':raise IsolationBlocked('Fresh base containment failed')
        proof=qualify(experiment,backend,output,approved_sha=approved_sha)
        if proof['status']!='PASS':raise IsolationBlocked('Benchmark state/model qualification failed')
        for row in experiment.data['matrix']:
            for variant in ('baseline','repair'):
                result=one(row,variant);benchmark.append(result)
        for family in ('rail','arm'):
            s=search(family,benchmark,one,budget=6,seed=experiment.data['search']['seed']);searches[family]=s
            if s['selected']:minimized[family]=minimize(s['selected'],one,budget=6)
            else:minimized[family]={'status':'NOT_APPLICABLE','reason':'No robustly measured controller counterexample found in this bounded coverage.'}
        status='COMPLETED'
    except (ValueError,OSError,RuntimeError) as exc:
        write_once(output/'failure.json',{'status':'BLOCKED','type':type(exc).__name__,'reason':str(exc)[:512]})
    finally:
        result={'status':status,'experiment_sha256':experiment.identity,'benchmark':benchmark,'searches':searches,'minimized':minimized,
                'all_results':all_results,'candidate_evaluations_dispatched':candidate_calls,
                'candidate_vm_sessions_upper_bound':candidate_calls*2,'elapsed_s':time.time()-started,'new_api_requests':0,
                'limitations':['Run the runtime cleanup/preflight check before claiming no VM remains. Dispatch counts bound attempted sessions, not proof all started.']}
        write_once(output/'batch.json',result)
    return result

"""Read-only frozen matrix, guard coverage and genuinely absent measurements."""
from pathlib import Path
from collections import Counter
from .contracts import Experiment
from .builder import approval_report
from .statistics import summary
from .ablation import diagnostic_ablation
from workspace.data import bounded_read,decode_json
from physics.contracts import digest


def offline_report(folder):
    folder=Path(folder);e=Experiment.load(folder);d=e.data;baseline=[]
    if (folder/'baseline_index.json').exists():
        index=decode_json(bounded_read(folder,'baseline_index.json'))
        if index.get('experiment_sha256')!=e.identity:raise ValueError('Baseline experiment identity mismatch')
        for item in index['results']:
            r=decode_json(bounded_read(folder,item['path']))
            if digest(r)!=item['sha256'] or r['variant']!='baseline':raise ValueError('Baseline evidence mismatch')
            baseline.append(r)
    return {'status':'PARTIAL','execution':'NOT_RUN_AWAITING_FRESH_VM_APPROVAL','experiment_sha256':e.identity,
        'sources':d['sources'],'sampling':d['sampling'],'seeds':d['seeds'],'parameters':d['parameters'],
        'matrix':d['matrix'],'guard_counts':{f:dict(Counter(r['guard']['status'] for r in d['matrix'] if r['family']==f)) for f in d['families']},
        'statistics':summary(baseline),'diagnostic_ablation':diagnostic_ablation(baseline),'counterexample_search':'NOT_EXECUTED',
        'trusted_baseline_rows':len(baseline),'trusted_baseline_measured':sum(r['execution']=='PASS' for r in baseline),
        'measured_pairs':0,'candidate_evaluations':0,'approval':approval_report(e),
        'claim':'Compiled physical models and trusted analytical bounds only. No new candidate robustness findings or failure-probability estimate.'}

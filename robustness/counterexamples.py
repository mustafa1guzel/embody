"""Transparent seeded local search, kept separate from frozen benchmark strata."""
import random
from .parameters import PARAMETERS,nominal
from .sampling import scenario
from .classification import objective


def search(family,benchmark,evaluate,budget=6,seed=1000003):
    if type(budget) is not int or not 0<=budget<=6:raise ValueError('Search budget out of scope')
    pool=[r for r in benchmark if r['family']==family and r['variant']=='repair'];trials=[];rng=random.Random(seed)
    for i in range(budget):
        worst=max(pool+trials,key=lambda r:(objective(r),r['scenario']['id'])) if pool or trials else None
        center=worst['scenario']['parameters'] if worst else nominal(family)
        p={k:min(v.high,max(v.low,center[k]+(rng.random()*2-1)*.1*(v.high-v.low))) for k,v in PARAMETERS[family].items()}
        trials.append(evaluate(scenario(family,p,'adaptive_search',i,seed)))
    found=[r for r in pool+trials if r.get('violations')]
    return {'status':'COMPLETED','seed':seed,'additional_evaluations':len(trials),'trials':trials,
            'counterexamples':found,'selected':max(found,key=lambda r:(objective(r),r['scenario']['id'])) if found else None,
            'claim':'Intentionally searched failures are not unbiased robustness observations.'}

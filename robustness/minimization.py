"""Measured coordinate simplification without assuming monotonicity."""
from .parameters import PARAMETERS,nominal,simplicity
from .sampling import scenario


def proposals(row):
    f=row['family'];p=row['parameters'];n=nominal(f)
    keys=sorted(p,key=lambda k:(-abs(p[k]-n[k])/(PARAMETERS[f][k].high-PARAMETERS[f][k].low),k))
    for key in keys:
        if abs(p[key]-n[key])<1e-12:continue
        for value in (n[key],(p[key]+n[key])/2):yield {**p,key:value}


def minimize(original,evaluate,budget=6):
    if type(budget) is not int or not 0<=budget<=6:raise ValueError('Minimization budget out of scope')
    if not original.get('violations'):return {'status':'NOT_APPLICABLE','trials':[]}
    requirement=max(original['violations'],key=lambda k:(original['violations'][k],k))
    best=original;trials=[];seen={tuple(sorted(original['scenario']['parameters'].items()))}
    while len(trials)<budget:
        proposal=next((p for p in proposals(best['scenario']) if tuple(sorted(p.items())) not in seen),None)
        if proposal is None:break
        seen.add(tuple(sorted(proposal.items())))
        row=scenario(original['family'],proposal,'minimization',len(trials),original['scenario']['seed'])
        result=evaluate(row);trials.append(result)
        if requirement in result.get('violations',{}) and simplicity(row['family'],proposal)<simplicity(best['family'],best['scenario']['parameters']):best=result
    # A fresh authoritative execution, not the saved command stream, confirms it.
    confirmed=evaluate(scenario(best['family'],best['scenario']['parameters'],'reproduction',0,original['scenario']['seed']))
    reproduced=requirement in confirmed.get('violations',{})
    return {'status':'REPRODUCED' if reproduced else 'NOT_REPRODUCED','requirement':requirement,'original':original,
            'selected':best,'confirmation':confirmed,'trials':trials,
            'simplicity_before':simplicity(original['family'],original['scenario']['parameters']),
            'simplicity_after':simplicity(best['family'],best['scenario']['parameters']),
            'claim':'Bounded greedy simplification; no monotonicity or global-minimum proof.'}

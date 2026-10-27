"""Conditional finite-sample summaries, with targeted search kept separate."""
import math
import statistics
from collections import Counter,defaultdict

VALID={'VERIFIED_WITHIN_TESTED_CONDITIONS','CONTROLLER_REQUIREMENT_FAILURE','CONTROLLER_SAFETY_VIOLATION'}


def wilson(successes,total,z=1.959963984540054):
    if type(total) is not int or type(successes) is not int or not 0<=successes<=total:raise ValueError('Invalid binary counts')
    if not total:return None
    p=successes/total;den=1+z*z/total;center=(p+z*z/(2*total))/den
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0.,center-half),min(1.,center+half)]


def summary(results):
    groups=defaultdict(list)
    for r in results:groups[(r['family'],r['variant'],r['scenario']['stratum'])].append(r)
    output=[]
    for (f,v,stratum),rows in sorted(groups.items()):
        valid=[r for r in rows if r['classification'] in VALID];success=sum(r['classification']=='VERIFIED_WITHIN_TESTED_CONDITIONS' for r in valid)
        keys=set().union(*(r.get('margins',{}) for r in valid)) if valid else set()
        margins={k:{'min':min(xs),'median':statistics.median(xs),'max':max(xs)} for k in sorted(keys) if (xs:=[r['margins'][k] for r in valid if k in r['margins']])}
        output.append({'family':f,'controller':v,'stratum':stratum,'total_rows':len(rows),'valid_evaluated':len(valid),
            'successes':success,'controller_failures':len(valid)-success,'classification_counts':dict(Counter(r['classification'] for r in rows)),
            'conditional_success_fraction':success/len(valid) if valid else None,
            'wilson_95':wilson(success,len(valid)) if stratum in ('nominal_uniform','wide_uniform') else None,
            'interval_scope':'Only conditional on valid outcomes in the stated IID parameter distribution; not real-world probability.',
            'margins':margins,'runtime_s':[r.get('elapsed_s') for r in rows],
            'severity_values':[r.get('severity',0.) for r in valid],
            'safety_violations':sum(r['classification']=='CONTROLLER_SAFETY_VIOLATION' for r in valid)})
    pairs=defaultdict(dict)
    for r in results:pairs[(r['family'],r['scenario']['stratum'],r['scenario']['id'])][r['variant']]=r
    paired=defaultdict(Counter)
    for (f,s,_),p in pairs.items():
        if set(p)!={'baseline','repair'} or any(r['classification'] not in VALID for r in p.values()):label='unavailable_or_task_infeasible'
        else:
            a=p['baseline']['classification']=='VERIFIED_WITHIN_TESTED_CONDITIONS';b=p['repair']['classification']=='VERIFIED_WITHIN_TESTED_CONDITIONS'
            label='both_pass' if a and b else 'both_fail' if not a and not b else 'baseline_fails_repair_passes' if b else 'baseline_passes_repair_fails'
        paired[(f,s)][label]+=1
    return {'groups':output,'paired':[{'family':f,'stratum':s,**dict(c)} for (f,s),c in sorted(paired.items())],
            'limitations':['No confidence interval for deliberately selected boundary, anchor or adaptive cases.',
                           'Failures are retained; missing/infeasible/unsupported outcomes are enumerated, never called successful.',
                           'These small conditional samples do not establish statistical significance or universal safety.']}

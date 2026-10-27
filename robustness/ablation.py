"""A diagnostic ablation never changes a frozen physical result."""
import time


def diagnostic_ablation(results,search_results=()):
    began=time.perf_counter();rows=[]
    for r in results:
        measured=r['execution']=='PASS' and r.get('independent_verification')=='PASS'
        violations=list(r.get('violations',{}));guard=r['guard']['status']
        # Explicit rubric: outcome, quantified margin, source/contract identity,
        # units/physical parameter context, and a scoped necessary-bound witness.
        for condition,contract,analytical in [('A_acceptance',False,False),('B_contract',True,False),('C_guard',False,True),('D_guard_search',True,True)]:
            condition_started=time.perf_counter()
            evidence={'measured_outcome':measured,'quantified_margin':measured and contract,
                      'bound_source_and_contract':contract,'units_and_physical_vector':contract,
                      'scoped_feasibility_explanation':analytical and guard!='UNKNOWN'}
            rows.append({'scenario_id':r['scenario']['id'],'family':r['family'],'variant':r['variant'],'condition':condition,
                'physical_outcome_unchanged':r['classification'],'violations_identified':violations if measured else [],
                'diagnostic_stage':'pre-execution task bound and post-simulation acceptance' if analytical else 'post-simulation acceptance' if measured else 'NO_MEASURED_RUN',
                'feasibility_claim':guard if analytical else 'NOT_ASSESSED','controller_program_proof':'UNKNOWN',
                'rubric':evidence,'rubric_count':sum(evidence.values()),'simulation_available':measured,
                'contradiction':bool(measured and r.get('physical_safety_status')=='PASS' and guard=='PROVEN_INFEASIBLE')})
            rows[-1]['diagnostic_transform_elapsed_s']=time.perf_counter()-condition_started
    return {'study':'Detection/diagnostic ablation, not repair generation','rows':rows,
        'rubric':'Count explicit evidence fields, not a subjective quality or truth score.',
        'diagnostic_transform_elapsed_s':time.perf_counter()-began,
        'timing_scope':'Measured report transformation only; not model inference or a counterfactual simulation cost.',
        'search_additional_evaluations':len(search_results),'search_counterexamples':sum(bool(r.get('violations')) for r in search_results),
        'search_changes_benchmark_outcomes':False,'repair_generation_ablation':'NOT_EXECUTED: separate independent model attempts/consent required',
        'limitations':['A detector removal cannot change an already frozen trajectory.',
                       'D reports additional search coverage separately, never an improved benchmark controller success rate.',
                       'NOT_RUN tasks provide no acceptance-only simulated outcome or causal counterfactual runtime claim.']}

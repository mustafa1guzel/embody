"""Deterministic factual report; user discussion never becomes measurement."""
from ide_api import rail_sweeps as rail

def escape(s):
 return str(s).replace('\\','\\\\').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('[','\\[').replace(']','\\]').replace('*','\\*').replace('_','\\_').replace('#','\\#').replace('\n',' ')

def generate(service,key,campaign_ids,hypothesis_ids,include_discussion=True):
 read=service.read(key);p=read['project']
 if not isinstance(campaign_ids,list) or len(set(campaign_ids))!=len(campaign_ids) or not set(campaign_ids)<={c['id'] for c in p['campaigns']}:raise ValueError('Exact selected campaigns required')
 if not isinstance(hypothesis_ids,list) or not set(hypothesis_ids)<={h['id'] for h in p['hypotheses']}:raise ValueError('Exact selected hypotheses required')
 views=[service.view(key,cid) for cid in campaign_ids];records={r['id']:r for v in views for r in v['records'] if r['verified']};n=len(records)
 result={'format':'EMBODY_RESEARCH_REPORT_V1','project_id':key,'project_sha256':read['sha256'],'title':p['title'],'kind':'SAVED_EVIDENCE_RESEARCH_ANALYSIS' if n else 'RESEARCH_PROPOSAL_ANALYTICAL_STUDY','question':p['question'],'hypotheses':[h for h in p['hypotheses'] if h['id'] in hypothesis_ids],'campaigns':[{k:v[k] for k in ('campaign','budgets','evidence_errors','boundary','sensitivity','benchmark','findings','completion_verified','evidence_completeness','resolution_history','residuals')} for v in views],'measured_cases':list(records.values()),'limitations':['Fixed rail proxy; finite sampled evidence, not universal safety or hardware certification.','No fresh native or paid provider run is performed by report generation.','External evidence is not execution of the proposed campaign.','Historical source identities remain historical; replay shares MuJoCo.','CIRCUITBASE is static validation, not electrical or coupled powertrain simulation.'],'ai_status':'UNAVAILABLE_NOT_CALLED'}
 lines=['# '+escape(p['title']),'','## Abstract',f'{n} unique independently read saved measured cases; {sum(r["verdict"]=="PASS" for r in records.values())} PASS and {sum(r["verdict"]=="FAIL" for r in records.values())} FAIL within their own recorded contracts. '+('No empirical completion claimed.' if not n else 'No new current-source experiment is claimed.'),'','## Research question',escape(p['question']),'','## Physical model','Registered rigid rail reference. Ideal braking: d = m v² / (2 F). Proposals, predictions, external measurements and campaign execution are separate.','','## Hypotheses']
 for h in result['hypotheses']:lines+=['- '+escape(h['content']['statement'])+' — '+h['status']+'; proposed relationship, not a proven fact.']
 for v in views:
  c=v['campaign'];lines+=['','## Campaign '+escape(c['config']['objective']),'### Methodology',f'Type {c["config"]["type"]}; strategy {c["config"]["strategy"]}; seed {c["config"]["seed"]}; controller {c["config"]["controller_id"]}.',f'State {c["status"]}; proposed {v["budgets"]["proposed"]}; submitted {v["budgets"]["submitted"]}. Research budget grants zero native authority.','Criteria: '+escape(c['config']['criteria']),'### Analytical predictions','Ideal derivatives and assumptions: '+escape(v['sensitivity']['analytical']),'### Failure-boundary analysis',escape(v['boundary']['status'])]
  for interval in v['boundary']['intervals']:lines+=['- '+escape(interval)]
  lines+=['### Measured finite differences',escape(v['sensitivity']['measured']),'### Controller comparison',escape(v['benchmark']['status']),'### Verified findings']
  for f in v['findings']:
   if f['status']=='VERIFIED':lines+=['- '+escape(f['fact']['metric'])+': '+str(f['fact']['value'])+' '+escape(f['fact']['unit'])+'; case '+f['fact']['case_id']+'; summary '+f['summary_sha256']]
   else:lines+=['- UNVERIFIED finding '+f['id']+'; unavailable evidence, no numerical claim retained.']
  if v['evidence_errors']:lines+=['Evidence verification unavailable; affected claims withheld: '+escape(v['evidence_errors'])]
 lines+=['','## Measured results and evidence references','| Case | Kind | Mass kg | Initial speed m/s | Force N | Initial gap m | Ideal stopping distance m | Ideal remaining gap m | Measured minimum gap m | Final speed m/s | Contacts | Sampled settled suffix s | Verdict | Replay |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|']
 for r in records.values():
  pcase=r['parameters'];m=r['metrics'];d=pcase['mass_kg']*pcase['speed_mps']**2/(2*pcase['force_n'])
  row=[r['id'],r['provenance_kind'],pcase['mass_kg'],pcase['speed_mps'],pcase['force_n'],pcase['gap_m'],d,pcase['gap_m']-d,m.get('minimum_clearance_m'),m.get('final_speed_mps'),m.get('wall_contact_episodes'),m.get('sampled_settling_time_s'),r['verdict'],(r['replay'].get('status',r['replay'].get('verification_execution','Unavailable')) if isinstance(r['replay'],dict) else r['replay'])]
  lines+=['| '+' | '.join('Unavailable' if x is None else str(x) for x in row)+' |',f'Case {r["id"]}: result {r["result_sha256"]}; trajectory {r["trajectory_sha256"]}; source current {r["source_current"]}.']
 if include_discussion:lines+=['','## Discussion','Observed extrema and sampled comparisons describe only saved compatible cases. A passing finite sample does not prove the unsampled domain. No observed transition is invented when all cases pass or conditions differ.']
 lines+=['','## Limitations',*['- '+x for x in result['limitations']],'','## Reproducibility',f'Project identity {read["sha256"]}. Export the versioned manifest for exact configurations, source/model/controller identities and saved evidence digests. Import never authorizes execution.','','## Future work','Review additional deterministic sampling proposals separately. Any new native demonstration or genuine model test requires a new exact approval.']
 result_benchmarks=[]
 for v in views:
  lines+=['','## Evidence completeness',escape(v['evidence_completeness']),'','## Resolution progress',escape(v['resolution_history']),'','## Prediction residuals','| Case | Continuous remaining gap m | Measured minimum gap m | Signed residual m | Relative residual |','|---|---:|---:|---:|---|']
  for row in v['residuals']:lines+=['| '+row['case_id']+' | '+str(row['analytical_value_m'])+' | '+str(row['measured_value_m'])+' | '+str(row['signed_residual_m'])+' | '+str(row['relative_residual'])+' |']
  for run in service.benchmarks.for_campaign(key,v['campaign']['id']):
   result_benchmarks.append(run);lines+=['','## Offline efficiency benchmark: '+escape(run['environment']['id']),run['environment']['provenance'],'| Strategy | Queries | Observed brackets | Smallest width | Queries to target | Termination |','|---|---:|---:|---:|---:|---|']
   for row in run['runs']:
    m=row['metrics'];lines+=['| '+row['strategy']+' | '+str(m['evaluated_points'])+' | '+str(m['observed_transition_count'])+' | '+str(m['smallest_observed_bracket_width'])+' | '+str(m['queries_to_target'])+' | '+m['termination']+' |']
 result['offline_benchmarks']=result_benchmarks
 result['markdown']='\n'.join(lines)+'\n';result['report_sha256']=rail.digest(result);return result

import {useEffect, useMemo, useRef, useState} from 'react';
import {api} from './api';
import {displayNumber as n, type Criteria, type RecordedSample} from './physicsRegression';
import {parameters, parameterKeys, type PhysicalParameters, type Plan} from './parameterSweep';
import RecordedTrajectoryPlot from './RecordedTrajectoryPlot';

type Catalog={experiment_id:string;controller_id:string;source_sha256:string;policy:{maximum_cases:number;primary_steps_per_case:number;replay_steps_per_case:number;wall_seconds:number};confirmation:string;limitations:string[];recent:{id:string;status:string}[]};
type Metrics={minimum_clearance_m:number;final_speed_mps:number;maximum_speed_mps:number;wall_contact_episodes:number;wall_contact_samples:number;sampled_settling_time_s:number|null;sampled_settling_travel_m:number|null;maximum_actuator_force_n:number};
type Case={case_id:string;parameters:PhysicalParameters;execution_status:string;verdict?:string;metrics?:Metrics;checks?:Record<string,boolean>;failure_reasons?:string[];error?:string;comparison?:{measured_minus_ideal_clearance_m:number;sampled_travel_minus_ideal_stop_m:number|null}};
type State={sweep_id:string;status:string;cases:Case[];error:string|null;request:{cases:PhysicalParameters[];criteria:Criteria;source_sha256:string;controller_id:string};limitations:string[]};
type Result=Case&{samples:RecordedSample[];source_sha256:string;controller_id:string;effective_model_sha256:string;trajectory_sha256:string;engine_version:string;analytical_prediction:{stopping_distance_m:number;stopping_time_s:number;remaining_clearance_m:number};replay:{status:string;primary_steps:number;fresh_steps:number}};
const terminal=(s:string)=>!['QUEUED','RUNNING'].includes(s);
function saveJSON(value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='embody-trusted-rail-sweep.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),0);}

export default function TrustedSweepPanel({plan}:{plan:Plan|null}){
 const [catalog,setCatalog]=useState<Catalog|null>(null),[error,setError]=useState(''),[reload,setReload]=useState(0);
 const [state,setState]=useState<State|null>(null),[confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[exporting,setExporting]=useState(false),[saved,setSaved]=useState('');
 const [selected,setSelected]=useState(''),[loaded,setResult]=useState<{key:string;value:Result}|null>(null),[mode,setMode]=useState('clearance');
 const result=loaded?.key===state?.sweep_id+':'+selected?loaded.value:null;
 const stalePlan=!!plan&&plan.controller_revision==='reference'&&!!catalog&&plan.initial_context.source_sha256!==catalog.source_sha256;
 const inFlight=useRef(false),generation=useRef(0),catalogGeneration=useRef(0);
 useEffect(()=>{let alive=true;setError('');const id=++catalogGeneration.current;api<Catalog>('rail-sweeps/catalog').then(c=>{if(alive&&id===catalogGeneration.current)setCatalog(c);}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[reload]);
 useEffect(()=>{setConfirm(false);},[plan]);
 useEffect(()=>{return()=>{generation.current++;};},[]);
 useEffect(()=>{
  if(!state||terminal(state.status))return;
  let alive=true;const key=state.sweep_id;const timer=setTimeout(()=>{
   api<State>('rail-sweeps/state?id='+key).then(s=>{if(alive)setState(s);}).catch(e=>{if(alive)setError('Progress read failed. Execution is not retried. '+String(e));});
  },500);return()=>{alive=false;clearTimeout(timer);};
 },[state]);
 useEffect(()=>{setResult(null);const row=state?.cases.find(c=>c.case_id===selected);if(!state||row?.execution_status!=='MEASURED')return;
  let alive=true;api<Result>('rail-sweeps/case?id='+state.sweep_id+'&case='+row.case_id).then(v=>{if(alive)setResult({key:state.sweep_id+':'+selected,value:v});}).catch(e=>{if(alive)setError('Saved case unavailable: '+String(e));});return()=>{alive=false;};
 },[state?.sweep_id,selected,state?.cases.find(c=>c.case_id===selected)?.execution_status]);
 async function load(id:string){if(!id)return;const g=++generation.current;setError('');setBusy(true);try{const s=await api<State>('rail-sweeps/state?id='+id);if(g===generation.current){setState(s);setSelected(s.cases[0]?.case_id||'');}}catch(e){if(g===generation.current)setError(String(e));}finally{if(g===generation.current)setBusy(false);}}
 async function start(){
  if(!catalog||!plan||stalePlan||inFlight.current)return;inFlight.current=true;setBusy(true);setConfirm(false);setError('');const g=++generation.current;
  const nonce=crypto.randomUUID().replaceAll('-','');
  try{const admitted=await api<{sweep_id:string}>('rail-sweeps/start',{experiment_id:catalog.experiment_id,controller_id:catalog.controller_id,source_sha256:catalog.source_sha256,cases:plan.cases.map(c=>c.parameters),criteria:plan.criteria,nonce,confirmation:catalog.confirmation});
   const s=await api<State>('rail-sweeps/state?id='+admitted.sweep_id);if(g===generation.current){setState(s);setSelected(s.cases[0]?.case_id||'');}
  }catch(e){if(g===generation.current)setError('Run not retried. Refresh saved runs to recover an uncertain admission. '+String(e));}
  finally{inFlight.current=false;if(g===generation.current)setBusy(false);}
 }
 async function cancel(){if(!state)return;try{setState(await api<State>('rail-sweeps/cancel',{id:state.sweep_id}));}catch(e){setError('Cancellation not confirmed. '+String(e));}}
 async function exportResults(){if(!state)return;setExporting(true);try{const cases=[];for(const c of state.cases)cases.push(c.execution_status==='MEASURED'?await api<Result>('rail-sweeps/case?id='+state.sweep_id+'&case='+c.case_id):c);saveJSON({format:'EMBODY_TRUSTED_RAIL_SWEEP_V1',...state,cases});}catch(e){setError('Export withheld: '+String(e));}finally{setExporting(false);}}
 const rows=state?.cases||[],measured=rows.filter(c=>c.execution_status==='MEASURED'&&c.metrics),running=!!state&&!terminal(state.status);
 const worst=measured.length?Math.min(...measured.map(c=>c.metrics!.minimum_clearance_m)):null;
 const largest=measured.length?Math.max(...measured.map(c=>Math.abs(c.comparison!.measured_minus_ideal_clearance_m))):null;
 const vary=parameterKeys.filter(k=>new Set(rows.map(c=>c.parameters[k])).size>1),x=vary.includes('speed_mps')?'speed_mps':vary[0]||'speed_mps',y=vary.find(k=>k!==x);
 const xs=[...new Set(rows.map(c=>c.parameters[x]))].sort((a,b)=>a-b),ys=y?[...new Set(rows.map(c=>c.parameters[y]))].sort((a,b)=>a-b):[null];
 const transitions=useMemo(()=>{
  const found:string[]=[];
  for(const k of parameterKeys)for(const a of measured)for(const b of measured){
   if(a.parameters[k]>=b.parameters[k]||a.verdict===b.verdict||parameterKeys.some(other=>other!==k&&a.parameters[other]!==b.parameters[other]))continue;
   if(rows.some(c=>parameterKeys.every(other=>other===k||c.parameters[other]===a.parameters[other])&&c.parameters[k]>a.parameters[k]&&c.parameters[k]<b.parameters[k]))continue;
   found.push(parameters[k].label+' '+a.parameters[k]+'–'+b.parameters[k]+' '+parameters[k].unit+'; other parameters fixed');
  }return found;
 },[state]);
 function cell(c:Case){const m=c.metrics;return <button className={'sweep-cell '+(c.execution_status==='MEASURED'?(c.verdict==='PASS'?'ideal-within':'ideal-outside'):'unavailable')+(selected===c.case_id?' selected':'')} aria-label={'Inspect measured case '+(rows.indexOf(c)+1)} aria-pressed={selected===c.case_id} onClick={()=>setSelected(c.case_id)}>
  <strong>{!m?c.execution_status.replaceAll('_',' '):mode==='clearance'?n(m.minimum_clearance_m)+' m':mode==='speed'?n(m.final_speed_mps)+' m/s':mode==='discrepancy'?n(c.comparison!.measured_minus_ideal_clearance_m)+' m':'Measured '+c.verdict}</strong><span>{m?'Measured '+c.verdict:c.error||'No measured verdict'}</span><small>Case {rows.indexOf(c)+1}</small></button>;}
 return <section className="sweep-native" aria-label="Trusted native sweep">
  <div className="regression-section-heading"><div><span className="regression-eyebrow">New local MuJoCo experiments · developer reference</span><h2>Run trusted reference simulations</h2></div><button onClick={()=>setReload(v=>v+1)}>Refresh saved sweeps</button></div>
  <p>Only the registered developer-authored velocity brake runs here. Historical original/repair selection above is for saved comparison; its source is never executed by this service.</p>
  {!catalog?<p role="status">Trusted execution catalog loading or unavailable. Analytical planning remains independent.</p>:<>
   <div className="sweep-native-toolbar"><label>Trusted experiment<select aria-label="Trusted experiment" value={catalog.experiment_id} onChange={()=>{}}><option value={catalog.experiment_id}>Rail · developer velocity brake v1</option></select></label><button disabled={!plan||busy||running||stalePlan} onClick={()=>setConfirm(true)}>Run Simulation Sweep</button><label>Saved sweeps<select aria-label="Saved sweeps" value={saved} onChange={e=>setSaved(e.target.value)}><option value="">Select a saved sweep</option>{catalog.recent?.map(r=><option key={r.id} value={r.id}>{r.id.slice(0,10)} · {r.status}</option>)}</select></label><button disabled={!saved||busy||running} onClick={()=>void load(saved)}>Load saved sweep</button></div>
   <p className="regression-note">1–4 kg · 0–1.2 m/s · 2–6 N · surface gap 0.35–2.2 m. Fixed 3 s at 0.005 s, 600 primary + 600 fresh replay steps per case; at most 25 cases serially, 60 s cooperative wall limit. No project application.</p>
   {confirm&&plan&&<div role="dialog" aria-label="Confirm trusted sweep" className="sweep-confirm"><h3>Confirm {plan.cases.length} new reference experiments</h3><p>Maximum {plan.cases.length*1200} native steps, including fresh replay; {catalog.policy.wall_seconds} seconds total. Uses current numerical grid and selected criteria, plus unchanged original reference safety checks. This is not execution of a historical or GPT-authored controller.</p><p className="regression-hash">Source/configuration: {catalog.source_sha256}</p><button disabled={busy} onClick={()=>void start()}>Confirm and run trusted sweep</button><button onClick={()=>setConfirm(false)}>Keep planning</button></div>}
  </>}
  {stalePlan&&<p role="alert">Reviewed proposal source is stale for the current native catalog. Return to the Designer for a new review.</p>}
  {error&&<p role="alert" className="regression-error">{error}</p>}{busy&&<p role="status">Reading / admitting explicit request…</p>}
  {state&&<><div aria-label="Native sweep progress" aria-live="polite"><h3>{state.status} · {measured.length} / {state.request.cases.length} measured</h3><progress value={measured.length} max={state.request.cases.length} aria-label="Measured case progress"/><p>{measured.filter(c=>c.verdict==='PASS').length} measured PASS · {measured.filter(c=>c.verdict==='FAIL').length} measured FAIL · worst observed clearance {n(worst)} m · largest absolute clearance discrepancy {n(largest)} m.</p>{state.error&&<p role="alert">{state.error}</p>}{running&&<button onClick={()=>void cancel()}>Cancel sweep</button>}<p>Selected criteria: clearance ≥ {state.request.criteria.minimumClearance} m; final |v| &lt; {state.request.criteria.maximumFinalSpeed} m/s; sampled settling ≤ {state.request.criteria.maximumSettlingTime} s; contact episodes ≤ {state.request.criteria.maximumContactEpisodes}. Fixed reference safety checks also remain mandatory.</p>{catalog&&state.request.source_sha256!==catalog.source_sha256&&<p className="regression-note">Saved source differs from the current trusted catalog. This is historical execution evidence, not a current-source verification.</p>}<p className="regression-note">Results belong to saved sweep {state.sweep_id.slice(0,12)} and its own exact request, even if the planning inputs above have changed.</p></div>
   <label>Measured heatmap mode<select aria-label="Measured heatmap mode" value={mode} onChange={e=>setMode(e.target.value)}><option value="clearance">Measured minimum clearance</option><option value="speed">Measured final speed</option><option value="status">Measured acceptance status</option><option value="discrepancy">Measured minus ideal clearance</option></select></label>
   <div className="regression-table-scroll">{vary.length<=2?<table className="sweep-grid"><caption>Measured grid · {parameters[x].label} →{y?' · '+parameters[y].label+' ↓':''}</caption><thead><tr><th>{y?parameters[y].unit:'Case'}</th>{xs.map(v=><th key={v}>{n(v)} {parameters[x].unit}</th>)}</tr></thead><tbody>{ys.map((v,i)=><tr key={i}><th scope="row">{v===null?'1':n(v)}</th>{xs.map(h=>{const c=rows.find(c=>c.parameters[x]===h&&(!y||c.parameters[y]===v));return <td key={h}>{c?cell(c):'Not planned'}</td>;})}</tr>)}</tbody></table>:<div className="sweep-native-list">{rows.map(c=><div key={c.case_id}>{cell(c)}</div>)}</div>}</div>
   <p className="regression-note">Each cell names its status. Color is supplementary. Prediction discrepancy compares measured minimum surface gap against the ideal remaining gap, in metres.</p>
   {rows.find(c=>c.case_id===selected)&&<section className="sweep-detail" aria-label="Native case details"><h3>Selected reference case · {rows.findIndex(c=>c.case_id===selected)+1}</h3><p>{rows.find(c=>c.case_id===selected)!.execution_status} · {rows.find(c=>c.case_id===selected)!.verdict||'No measured verdict'}</p><p>{parameterKeys.map(k=>parameters[k].label+' '+rows.find(c=>c.case_id===selected)!.parameters[k]+' '+parameters[k].unit).join(' · ')}</p>
    {result?<><p>MuJoCo {result.engine_version} · fresh replay {result.replay.status} · {result.replay.primary_steps}+{result.replay.fresh_steps} native steps</p><dl>{Object.entries(result.metrics!).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{n(value)}</dd></div>)}</dl><p>Ideal stopping distance {n(result.analytical_prediction.stopping_distance_m)} m; time {n(result.analytical_prediction.stopping_time_s)} s; remaining gap {n(result.analytical_prediction.remaining_clearance_m)} m.</p><p>Measured minus ideal clearance: {n(result.comparison!.measured_minus_ideal_clearance_m)} m. Sampled settling travel minus ideal stop: {n(result.comparison!.sampled_travel_minus_ideal_stop_m)} m; different stopping definitions.</p><ul>{Object.entries(result.checks!).map(([k,v])=><li key={k}>{v?'PASS':'FAIL'} · {k.replaceAll('_',' ')}</li>)}</ul><p>{result.failure_reasons!.join('; ')||'All fixed reference and selected checks passed for this finite case.'}</p><details><summary>Exact measured provenance</summary><p className="regression-hash">Controller: {result.controller_id}<br/>Source/configuration SHA-256: {result.source_sha256}<br/>Effective model SHA-256: {result.effective_model_sha256}<br/>Trajectory SHA-256: {result.trajectory_sha256}</p></details><RecordedTrajectoryPlot runs={[{id:result.case_id,title:'Trusted developer reference · case '+(rows.findIndex(c=>c.case_id===selected)+1),revision:'reference',samples:result.samples,timeValid:true}]} criteria={state.request.criteria}/></>:<p>No verified trajectory loaded for this case. Queued, running, cancelled and errored cases are not measured PASS.</p>}
   </section>}
   <div aria-label="Measured boundary analysis"><h3>Observed sampled boundaries</h3><p>{transitions.length?transitions.join('; '):'No adjacent measured PASS/FAIL transition in the available cases. Unexecuted/error gaps never establish a boundary.'}</p><p>Failed sampled cases: {measured.filter(c=>c.verdict==='FAIL').map(c=>'case '+(rows.indexOf(c)+1)).join(', ')||'None among measured cases'}.</p></div>
   <button disabled={exporting||running} onClick={()=>void exportResults()}>{exporting?'Reading verified cases…':'Export measured sweep JSON'}</button>
  </>}
  <details><summary>Trusted execution limits and security</summary><ul>{(catalog?.limitations||state?.limitations||[]).map(t=><li key={t}>{t}</li>)}</ul><p>Local Host/Origin/CSRF guards, one shared expensive job, source-bound admission and append-only case records. No arbitrary source, XML, module, executable or output path is accepted. Cancellation preserves completed cases; uncertain or interrupted requests are never automatically retried. Results are retained under ignored local runtime storage, separately from historical evidence.</p></details>
 </section>;
}

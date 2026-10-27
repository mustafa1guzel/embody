import {useEffect,useState} from 'react';
import {api} from './api';
import type {Variant} from './types';

type Assessment={status:string;explanation:string;bounds:Record<string,number>;equations:Record<string,string>;assumptions:string[];unsupported:string[]};
type Metric={status:string;value:number|null;unit:string;method:string};
export type PhysicsReport={scenario_id:string;variant:Variant;contract_sha256:string;report_sha256:string;evidence_kind:string;
 physics_contract:{mass_kg:number;generalized_inertia_kg:number;braking_force_n:number;timestep_s:number;model_sha256:string;controller_sha256:string;wall_near_x_m:number;initial_clearance_m:number};
 analytical_feasibility:Assessment;controller_static_assessment:{status:string;explanation:string};
 observed_physics:{safety_status:string;minimum_clearance_m:number;clearance_margin_m:number;final_absolute_velocity_mps:number;violations:string[]};
 braking_onset:{time_s:number;clearance_m:number;velocity_mps:number;analysis:Assessment}|null;
 profiler:{metrics:Record<string,Metric>};outside_envelope:Assessment;recorded_independent_verification:string;uncertainty:string[]};

const number=(v:number|undefined)=>v===undefined?'NOT_AVAILABLE':Number(v.toPrecision(8)).toString();
export default function PhysicsPanel({scenario,variant}:{scenario:string;variant:Variant}){
 const [report,setReport]=useState<PhysicsReport|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  let current=true;setReport(null);setError('');
  api<PhysicsReport>('physics?scenario='+encodeURIComponent(scenario)+'&variant='+encodeURIComponent(variant)).then(r=>{
   if(!current)return;
   if(r.scenario_id!==scenario||r.variant!==variant||!r.contract_sha256||!r.analytical_feasibility?.bounds||!r.profiler?.metrics
     ||!['PROVEN_VIOLATION','PROVEN_INFEASIBLE','CONDITIONALLY_FEASIBLE','UNKNOWN'].includes(r.analytical_feasibility.status)
     ||!r.physics_contract||!r.observed_physics||!['PASS','FAIL'].includes(r.observed_physics.safety_status)
     ||!r.analytical_feasibility.assumptions||!r.analytical_feasibility.equations
     ||!r.controller_static_assessment||!r.outside_envelope||!Array.isArray(r.uncertainty))throw new Error('Physics report identity or schema mismatch');
   setReport(r);
  }).catch(e=>{if(current)setError(String(e));});
  return()=>{current=false;};
 },[scenario,variant]);
 if(error)return <p role="alert" className="danger">Physics analysis BLOCKED: {error}. No fallback verdict.</p>;
 if(!report||report.scenario_id!==scenario||report.variant!==variant)return <p className="note">Loading deterministic physics analysis…</p>;
 const c=report.physics_contract,a=report.analytical_feasibility,o=report.observed_physics,onset=report.braking_onset;
 return <section className="physics-panel" aria-label="Physics contract and analysis">
  <p className="note">New deterministic analysis of recorded measurements · scenario {scenario} / {variant} · no new model or simulation execution.</p>
  <div className="physics-verdicts"><span>Task model: <strong>{a.status}</strong></span><span>Recorded safety: <strong className={o.safety_status==='PASS'?'success':'danger'}>{o.safety_status}</strong></span><span>Program proof: <strong>{report.controller_static_assessment.status}</strong></span></div>
  <p>{a.explanation}</p>
  <table><thead><tr><th>Physical quantity</th><th>Value</th><th>Meaning</th></tr></thead><tbody>
   <tr><td>Body / generalized mass</td><td>{c.mass_kg} / {c.generalized_inertia_kg} kg</td><td>Compiled inertia checked independently</td></tr>
   <tr><td>Braking authority / deceleration</td><td>{c.braking_force_n} N / {number(a.bounds.deceleration_mps2)} m/s²</td><td>Checked transmission, gain and force clamps</td></tr>
   <tr><td>Ideal zero-stop distance</td><td>{number(a.bounds.continuous_zero_stop_m)} m</td><td>Continuous constant-force reference</td></tr>
   <tr><td>Discrete zero-stop travel</td><td>{number(a.bounds.discrete_zero_stop_m)} m</td><td>Constructive fractional final command; no program certificate</td></tr>
   <tr><td>Initial surface gap / wall near face</td><td>{number(c.initial_clearance_m)} / {number(c.wall_near_x_m)} m</td><td>Geometric surfaces, not wall-center distance</td></tr>
   <tr><td>Measured minimum gap / margin</td><td>{number(o.minimum_clearance_m)} / {number(o.clearance_margin_m)} m</td><td>Exact recorded trajectory versus clearance requirement</td></tr>
   <tr><td>Recorded final |velocity|</td><td>{number(o.final_absolute_velocity_mps)} m/s</td><td>Finite tested horizon only</td></tr>
  </tbody></table>
  {onset&&<p>Measured braking onset: {number(onset.time_s)} s, gap {number(onset.clearance_m)} m, speed {number(onset.velocity_mps)} m/s. <strong>{onset.analysis.status}</strong> — {onset.analysis.explanation}</p>}
  <p className="note">Recorded independent verification: {report.recorded_independent_verification}. Violations: {o.violations.join(', ')||'none in these samples'}. Outside envelope: {report.outside_envelope.status}.</p>
  <details><summary>Derivation, assumptions and bounds</summary>{Object.entries(a.equations).map(([key,value])=><p key={key}><code>{value}</code></p>)}<ul>{a.assumptions.map(s=><li key={s}>{s}</li>)}</ul><pre>{JSON.stringify({initial_bounds:a.bounds,onset_bounds:onset?.analysis.bounds,unsupported:a.unsupported},null,2)}</pre></details>
  <details><summary>Physical metrics and calculation methods</summary><table><thead><tr><th>Metric</th><th>Value</th><th>Method</th></tr></thead><tbody>{Object.entries(report.profiler.metrics).map(([key,m])=><tr key={key}><td>{key.replaceAll('_',' ')}</td><td>{m.status==='AVAILABLE'&&m.value!==null?number(m.value)+' '+m.unit:'NOT_AVAILABLE'}</td><td>{m.method}</td></tr>)}</tbody></table></details>
  <details><summary>Evidence identities and limitations</summary><p className="hash">Contract {report.contract_sha256}<br/>Model {c.model_sha256}<br/>Controller {c.controller_sha256}<br/>Report {report.report_sha256}</p><ul>{report.uncertainty.map(s=><li key={s}>{s}</li>)}</ul><pre>{JSON.stringify(report,null,2)}</pre></details>
  <p className="note">Analysis grants no VM or apply approval. Verification and permanent application remain separate explicit actions in the existing review workflow.</p>
 </section>;
}

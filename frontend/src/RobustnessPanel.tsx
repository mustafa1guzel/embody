import {useEffect,useState} from 'react';
import {api} from './api';
export default function RobustnessPanel(){
 const [report,setReport]=useState<any>(null),[error,setError]=useState(''),[family,setFamily]=useState('rail');
 useEffect(()=>{let alive=true;api('robustness').then(r=>{if(alive)setReport(r);}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[]);
 if(error)return <p role="alert">Robustness BLOCKED: {error}</p>;
 if(!report)return <p>Loading frozen physical variations…</p>;
 return <section className="robustness-panel"><h3>Physical robustness / counterexamples</h3><p><strong>{report.status}</strong> · {report.execution}</p><p>{report.claim}</p><p>Experiment <code>{report.experiment_sha256}</code></p><label>Family<select aria-label="Robustness family" value={family} onChange={e=>setFamily(e.target.value)}><option value="rail">Rail carriage</option><option value="arm">Planar arm</option></select></label><p>{report.sampling}</p><p>{report.measured_pairs} new measured pairs · counterexample search {report.counterexample_search}</p>
  <table><thead><tr><th>Frozen scenario</th><th>Stratum / seed</th><th>Actual physical parameters (SI)</th><th>Analytical task status</th></tr></thead><tbody>{report.matrix.filter((r:any)=>r.family===family).map((r:any)=><tr key={r.id}><td><details><summary>{r.id}</summary><code>{r.model_sha256}</code></details></td><td>{r.stratum}<br/>{r.seed}</td><td>{Object.entries(r.parameters).map(([k,v])=><span className="parameter" key={k}>{k}: {String(v)} </span>)}</td><td>{r.guard.status}</td></tr>)}</tbody></table>
  <details><summary>Frozen source provenance and precise VM approval scope</summary><pre>{JSON.stringify({sources:report.sources,approval:report.approval},null,2)}</pre></details><p className="note">Historical nominal success is not a new robustness measurement. No execution or spending action is available here.</p></section>;
}

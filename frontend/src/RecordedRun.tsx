import {useEffect,useState} from 'react';
import {Check,FileCode2,GitPullRequest,Copy,ArrowUpRight,AlertTriangle} from 'lucide-react';
import type {FileData,RecordedAgent} from './types';
import {api} from './api';

export default function RecordedRun({recorded,onProposal,onFile}:{recorded:RecordedAgent;onProposal?:(variant:'attempt_1'|'attempt_2',diff:boolean)=>void;onFile?:(path:string)=>void}){
 const [question,setQuestion]=useState(''),[error,setError]=useState(''),[copyStatus,setCopyStatus]=useState(''),[detailsOpen,setDetailsOpen]=useState(false);
 useEffect(()=>{let alive=true;api<FileData>('file?path='+encodeURIComponent('recording/agent_trace.jsonl')).then(file=>{
  const item=file.content.split('\n').filter(Boolean).map(line=>JSON.parse(line)).find(row=>row.event==='user_request');
  if(!item||typeof item.payload?.text!=='string')throw new Error('Recorded user task is missing');
  if(alive)setQuestion(item.payload.text);
 }).catch(()=>{if(alive)setError('Recorded task unavailable. Inspect the preserved trace.');});return()=>{alive=false;};},[]);
 const baselines=recorded.calls.filter(c=>c.name==='run_simulation').map(c=>(c.output as any)?.result).filter(Boolean);
 const proposals=recorded.calls.filter(c=>c.name==='propose_patch');
 const reads=recorded.calls.filter(c=>c.name==='read_project').length;
 async function copy(value:unknown){try{await navigator.clipboard.writeText(typeof value==='string'?value:JSON.stringify(value,null,2));setCopyStatus('Copied exact evidence');}catch{setCopyStatus('Copy unavailable. Open the trace to select text.');}}
 return <div className="recorded-run">
  <div className="recording-badge">RECORDED · GPT-5.4 · DAY 4B.2</div>
  <div className="user-question"><span className="thread-label">User question</span>{question?<p>{question}</p>:<p className="note">{error||'Loading saved task…'}</p>}</div>
  <div className="run-summary"><div className="summary-heading"><Check size={14}/><strong>{recorded.result.orchestration_status==='COMPLETED'?'Investigation completed':'Investigation '+recorded.result.orchestration_status}</strong><span>{recorded.calls.length} calls</span></div>
   <div className="run-step"><FileCode2 size={14}/><div><strong>Read project</strong><small>{reads} source reads · BODYBASE + WORLDBASE</small></div>{onFile&&<button title="Open original controller" aria-label="Open original controller" onClick={()=>onFile('robot/controller.py')}><ArrowUpRight size={13}/></button>}</div>
   <div className="run-step"><AlertTriangle size={14}/><div><strong>Baseline {baselines.length&&baselines.every(s=>s.physical_safety_status==='FAIL')?'failed':'measured'}</strong><small>{baselines.map(s=>s.scenario_id+': '+s.physical_safety_status).join(' · ')||'No baseline result in this trace'}</small></div></div>
  </div>
  <div className="patch-iterations">{proposals.map((call,i)=>{
   const validation=(call.output as any)?.result,verification=call.verification_feedback as any;
   const verified=verification?.verification_execution==='PASS'&&verification?.physical_safety_status==='PASS';
   const scenarios=Object.entries(verification?.scenario_results||{}) as [string,any][];
   const variant=i===0?'attempt_1':'attempt_2';
   return <section className="patch-iteration" key={i}><div className="patch-heading"><GitPullRequest size={15}/><strong>Proposal {i+1}</strong><span className={'result-pill '+(verified?'success':'danger')}>{verified?'Verified':verification?.physical_safety_status==='FAIL'?'Safety rejected':validation?.validation_status||'Not verified'}</span></div>
    <p className="patch-target">robot/controller.py <code>{validation?.proposed_sha256?.slice(0,10)}</code></p>
    <div className="scenario-outcomes">{scenarios.map(([name,s])=><span key={name} className={s.physical_safety_status==='PASS'?'success':'danger'}>{name} <strong>{s.physical_safety_status}</strong><small>{s.minimum_clearance_m?.toFixed(4)} m gap</small></span>)}</div>
    <details className="proposal-explanation"><summary>Original model explanation</summary><p>{(call.arguments as any)?.explanation}</p></details>
    {onProposal&&<div className="patch-actions"><button onClick={()=>onProposal(variant,false)}>Review patch</button><button onClick={()=>onProposal(variant,true)}>Open diff <ArrowUpRight size={12}/></button></div>}
   </section>;
  })}</div>
  <details className="run-details" onToggle={event=>setDetailsOpen(event.currentTarget.open)}><summary>Run details · {recorded.calls.length} tool calls</summary>{detailsOpen&&<>{onFile&&<button onClick={()=>onFile('recording/agent_trace.jsonl')}>Open trace <ArrowUpRight size={12}/></button>}{recorded.calls.map((call,i)=><details className="tool-call" key={i}><summary><code>{String(i+1).padStart(2,'0')} {call.name}</code></summary><div className="evidence-actions"><button onClick={()=>copy(call.arguments)}><Copy size={12}/>Copy input</button><button onClick={()=>copy(call.output)}><Copy size={12}/>Copy output</button></div><pre>{JSON.stringify(call.arguments,null,2)}</pre><pre>{JSON.stringify(call.output,null,2)}</pre>{call.verification_feedback!==undefined&&<details><summary>Independent verification feedback</summary><pre>{JSON.stringify(call.verification_feedback,null,2)}</pre></details>}</details>)}</>}</details>
  <details className="model-conclusion"><summary>Original model conclusion</summary><pre className="prose">{recorded.diagnosis}</pre><button onClick={()=>copy(recorded.diagnosis)}>Copy conclusion</button></details>
  {copyStatus&&<p role="status" className="note">{copyStatus}</p>}
  <div className="recorded-cost">Recorded cost <code>${recorded.result.api_budget.measured_cost_usd}</code></div>
 </div>;
}

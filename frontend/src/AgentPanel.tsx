import {useEffect,useState} from 'react';
import {Bot,Send,Focus} from 'lucide-react';
import RecordedRun from './RecordedRun';
import {api,job} from './api';
import type {Bootstrap,RecordedAgent} from './types';
export default function AgentPanel({recorded,bootstrap,references,onFocus,onReview,onProposal,onFile}:{recorded:RecordedAgent;bootstrap:Bootstrap;references:string[];onFocus:()=>void;onReview:(id:string)=>void;onProposal?:(variant:'attempt_1'|'attempt_2',diff:boolean)=>void;onFile?:(path:string)=>void}){
 const [source,setSource]=useState<'recorded'|'live'>('recorded'),[workflow,setWorkflow]=useState<'code'|'physical'>('physical'),[message,setMessage]=useState(''),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[error,setError]=useState(''),[history,setHistory]=useState<{role:string;text:string}[]>([]),[live,setLive]=useState<any>(null);
 // Component stays mounted across mode changes, retaining conversation identity.
 useEffect(()=>()=>{},[]);
 const authorizedReferences=references.filter(p=>!p.startsWith('recording/')).slice(0,4);
 async function start(){
  if(!consent||!message.trim()||busy)return;
  setBusy(true);setError('');setLive(null);const prompt=message;setMessage('');setHistory(h=>[...h,{role:'user',text:prompt}]);
  try{const result=await job<any>('agent/start',{mode:workflow,message:prompt,references:authorizedReferences,confirmation:bootstrap.live_policy.consent},setProgress);setLive(result);setHistory(h=>[...h,result.model_final_text?{role:'agent',text:result.model_final_text}:{role:'status',text:'No final model text. See actual status and evidence.'}]);setProgress(result.orchestration_status);}
  catch(e){setError(String(e));setProgress('BLOCKED — no automatic retry');}
  finally{setBusy(false);setConsent(false);}
 }
 return <aside className="agent-panel"><div className="panel-title"><Bot size={16}/><strong>EMBODY Agent</strong><span className="spacer"/><button onClick={onFocus} aria-label="Focus or restore agent" title="Focus / restore agent"><Focus size={14}/></button></div>
  <div className="agent-source"><button aria-pressed={source==='recorded'} onClick={()=>setSource('recorded')}>Recorded evidence</button><button aria-pressed={source==='live'} onClick={()=>setSource('live')}>New live session</button></div>
  {source==='live'&&<div className="agent-workflow"><label>Workflow<select value={workflow} onChange={e=>setWorkflow(e.target.value as typeof workflow)} disabled={busy}><option value="physical">Physical debug · six tools</option><option value="code">Code assistance · source read only</option></select></label><small>GPT-5.4 / low</small></div>}
  <div className="agent-scroll">{source==='recorded'?<RecordedRun recorded={recorded} onProposal={onProposal} onFile={onFile}/>:<>
   {!history.length&&<div className="agent-empty"><Bot size={24}/><h3>Work on the physical problem.</h3><p>Reference source, inspect measured behavior, then review a proposal.</p><small>No session has started.</small></div>}
   {history.map((entry,i)=><div className={'thread-entry '+entry.role} key={i}><small>{entry.role==='agent'?'GENUINE LIVE MODEL OUTPUT':entry.role==='user'?'User':'LOCAL SESSION STATUS'}</small><pre className="prose">{entry.text}</pre></div>)}
   {live&&<div className="live-result"><p>Session {live.orchestration_status} <code>${live.api_budget.measured_cost_usd}</code></p><small>Conservatively accounted: ${live.api_budget.accounted_cost_usd}</small><details><summary>Genuine tool / model activity</summary><pre>{JSON.stringify(live.events,null,2)}</pre></details>{live.review_ids.map((id:string)=><button key={id} onClick={()=>onReview(id)}>Inspect review {id.slice(0,8)}</button>)}</div>}
  </>}</div>
  {source==='live'&&<div className="agent-composer">
   <div className="references" title="Only authorized project files are sent. Historical tabs are excluded.">{authorizedReferences.map(p=><code key={p}>{p}</code>)}</div>
   <label className="composer-label">Describe the problem<textarea value={message} maxLength={8000} onChange={e=>setMessage(e.target.value)} placeholder="Ask about code or measured behavior…" disabled={busy}/></label>
   <details className="budget-details"><summary>Budget & permissions · max $0.50</summary><p>New session per send. GPT-5.4 / low; 6 requests, 16 tool calls, 2 proposals, $0.50 session cap, $30 cumulative cap. Reasoning is included in output cost. No model fallback or automatic retry. Proposals require separate VM and apply approvals.</p></details>
   <label className="consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} disabled={busy}/>I authorize this new GPT-5.4 / low session up to $0.50. No candidate execution or installation is approved.</label>
   <button className="primary send" onClick={start} disabled={!consent||!message.trim()||busy}><Send size={13}/>{busy?'Agent running…':'Start genuine agent session'}</button>
   {progress&&<p role="status" className="note">{progress}</p>}{error&&<p className="error" role="alert">{error}</p>}
  </div>}
  <div className="agent-footer" title="Recorded results are historical. No automatic inference or execution. Verification and installation require separate approvals."><span className={'status-dot '+(busy?'running':'')}/>{busy?'Live session active':source==='recorded'?'Historical session · read only':'Awaiting explicit approval'}<span className="spacer"/><span>{source==='recorded'?'$0 to view':'$0.50 limit'}</span></div>
 </aside>;
}

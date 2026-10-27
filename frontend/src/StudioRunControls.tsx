import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import Exact from './EngineeringDetails';
import type {Activity} from './engineeringExperience';

export function executionActivity(state:any):Activity|null{
 if(!state?.active)return state?.stage==='UNKNOWN_OUTCOME'?{title:'Unknown outcome',message:'No live worker is confirmed. Read the execution and cost records before retrying.'}:null;
 const stages:Record<string,Activity>={
 awaiting_native_confirmation:{title:'Confirm in the Mac window',message:'AI has not started. The native operator confirmation is waiting.'},
 model_request_started:{title:'Waiting for AI response',message:'An authorized transport attempt is recorded; the live local worker is waiting for its result.'},
 model_response_received:{title:'AI response received',message:'Reading the actual returned engineering arguments.'},
 reading_engineering_state:{title:'Reading engineering state',message:'Providing the real project and supported contracts.'},
 validating_operations:{title:'Validating proposed operations',message:'The existing typed compiler is checking the supplied design.'},
 geometry_compiled:{title:'Design geometry compiled',message:'The proposal exists; physical verification is still separate.'},
 native_simulation_started:{title:'Running permitted physics',message:'The trusted 200-step preview and fresh replay were explicitly authorized.'},
 verification_completed:{title:'Verification recorded',message:'Reading the actual measured result; no proposal is applied.'}};
 return stages[state.stage]||{title:'Authorized local worker',message:'A live local job is confirmed. Waiting for its next recorded event.'};
}

export default function StudioRunControls({request,onRefresh,onActivity,autoReview=0}:{request:any;autoReview?:number;onRefresh:()=>Promise<any>;onActivity:(a:Activity|null)=>void}){
 const [quote,setQuote]=useState<any>(null),[state,setState]=useState<any>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const modal=useRef<HTMLDialogElement>(null),alive=useRef(true),refresh=useRef(onRefresh),sink=useRef(onActivity),timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);refresh.current=onRefresh;sink.current=onActivity;
 useEffect(()=>{if(quote&&modal.current&&!modal.current.open)modal.current.showModal();},[quote]);
 useEffect(()=>{
  alive.current=true;let last='';
  async function poll(){try{const value=await api<any>('ai-engineering/execution-status?id='+request.request_id);if(!alive.current)return;setState(value);sink.current(executionActivity(value));
    if((value.finished||value.stage==='UNKNOWN_OUTCOME')&&last!==value.stage){last=value.stage;await refresh.current();}
    if(value.active&&alive.current)timer.current=setTimeout(poll,1500);
   }catch{if(alive.current){setError('Execution status could not be read. Do not retry a potentially billable run; check its record.');sink.current({title:'Unknown outcome',message:'The execution record could not be refreshed. No completion or charge outcome is inferred.'});}}}
  void poll();return()=>{alive.current=false;clearTimeout(timer.current);};
 },[request.request_id]);
 useEffect(()=>{if(autoReview&&request.status==='PENDING_APPROVAL')void review();},[autoReview]);
 async function review(){if(busy)return;setBusy(true);setError('');try{const q=await api('ai-engineering/review-run',{request_id:request.request_id});if(alive.current)setQuote(q);}catch(e){if(alive.current)setError(String(e));}finally{if(alive.current)setBusy(false);}}
 async function start(){if(busy||!quote)return;setBusy(true);setError('');sink.current({title:'Requesting Mac confirmation',message:'Contacting the local authorization service. AI has not been confirmed started.'});try{
   await api('ai-engineering/start-building',{review_id:quote.review_id});if(!alive.current)return;setQuote(null);
   // Poll only the actual server record; never resubmit a start after uncertainty.
   async function read(){try{const v=await api<any>('ai-engineering/execution-status?id='+request.request_id);if(!alive.current)return;setState(v);sink.current(executionActivity(v));if(v.active)timer.current=setTimeout(read,1500);else await refresh.current();}catch{if(alive.current){setError('Initiation outcome is unknown. Check execution records before any further action.');sink.current({title:'Unknown outcome',message:'Do not retry the paid request blindly.'});}}}
   clearTimeout(timer.current);void read();
  }catch(e){if(alive.current){setError('Start could not be confirmed. No retry was issued. Check the execution record. '+String(e));sink.current({title:'Unknown outcome',message:'Initiation could not be confirmed. Check the saved execution and cost records.'});}}
  finally{if(alive.current)setBusy(false);}
 }
 return <section className="studio-run-controls" aria-label="Authorized engineering execution">
  {request.status==='PENDING_APPROVAL'&&!state?.active&&!state?.finished&&<button className="studio-primary" disabled={busy} onClick={()=>void review()}>Build robot</button>}
  {state?.active&&<p role="status">{executionActivity(state)?.title}. Switching panels does not restart this job.</p>}
  {state?.finished?.status==='OPERATOR_DECLINED'&&<p>Native confirmation was declined. No model execution started. Cancel this request before preparing another.</p>}
  {state?.finished?.message&&<p>{state.finished.message}</p>}
  {state?.events?.length>0&&<details><summary>Actual execution events</summary><ol>{state.events.map((e:any,i:number)=><li key={i}>{e.event.replaceAll('_',' ')} · {new Date(e.recorded_unix*1000).toLocaleTimeString()}</li>)}</ol></details>}
  {error&&<div role="alert"><p>{error}</p><button onClick={()=>void refresh.current()}>Check saved request</button></div>}
  {quote&&<dialog ref={modal} className="studio-run-dialog" aria-label="Review AI run" onCancel={()=>setQuote(null)}>
   <h3>Build this robot?</h3><p>{quote.task}</p><p>This AI run may cost up to <strong>${quote.policy.hard_cap_usd} USD</strong>. Nothing is applied automatically.</p><p>{quote.policy.native_previews?'Movement testing is included in this exact authorization.':'Geometry review only; movement testing is not included.'}</p>
   <p>Start building opens a Mac confirmation window. AI begins only after you confirm that exact request there.</p>
   <details><summary>Usage & Safety</summary><dl><dt>Model</dt><dd>GPT-5.4 · low reasoning</dd><dt>Reservation</dt><dd>≤${quote.policy.maximum_reservation_usd}</dd><dt>Provider requests</dt><dd>At most {quote.policy.max_requests}; no retries or fallback.</dd><dt>Physics</dt><dd>{quote.policy.native_previews?'One trusted preview and fresh replay.':'Not authorized. Geometry validation only.'}</dd></dl><Exact title="Exact frozen request and authorization identity" value={quote}/></details>
   {!quote.native_confirmation_supported&&<p role="alert">Native confirmation is unavailable here. Execution cannot start from this studio. Use the separately approved local operator workflow.</p>}
   <div className="studio-actions"><button onClick={()=>setQuote(null)}>Back to request</button><button className="studio-primary" disabled={busy||!quote.native_confirmation_supported} onClick={()=>void start()}>Start building</button></div>
  </dialog>}
 </section>;
}

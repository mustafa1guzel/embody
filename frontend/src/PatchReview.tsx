import {useEffect,useState} from 'react';
import {api,job} from './api';
import type {Proposal} from './types';
import {UnifiedDiff} from './UnifiedDiff';
export default function PatchReview({proposal,variant,resumeId,onDiff,onReview,errorReport,family='rail'}:{family?:'rail'|'arm';proposal:Proposal;variant:string;resumeId:string;onDiff:(source?:{original:string;modified:string})=>void;onReview:(id:string)=>void;errorReport:(message:string)=>void}){
 const prefix=family==='arm'?'arm/':'';
 const [review,setReview]=useState<Record<string,any>|null>(null),[id,setId]=useState(''),[busy,setBusy]=useState(false),[progress,setProgress]=useState(''),[verifyConsent,setVerifyConsent]=useState(false),[confirmation,setConfirmation]=useState('');
 async function perform(action:()=>Promise<any>){setBusy(true);setProgress('Working…');try{const result=await action();if(result?.review_id){setId(result.review_id);onReview(result.review_id);setReview(await api(prefix+'review?id='+result.review_id));}else if(result)setReview(result);setProgress('Operation finished; inspect its status below.');}catch(e){errorReport(String(e));setProgress('BLOCKED');}finally{setBusy(false);}}
 useEffect(()=>{if(!resumeId)return;let alive=true;api<Record<string,any>>(prefix+'review?id='+encodeURIComponent(resumeId)).then(r=>{if(alive){setId(resumeId);setReview(r);}}).catch(e=>{if(alive)errorReport(String(e));});return()=>{alive=false;};},[resumeId,errorReport,prefix]);
 const validation=review?.validation||proposal.validation;
 async function openDiff(){try{onDiff(review?await api<{original:string;modified:string}>(prefix+'review/source?id='+review.review_id):undefined);}catch(e){errorReport(String(e));}}
 return <section className="review-panel"><div className="section-heading"><span>PATCH REVIEW</span><button onClick={openDiff}>Open Monaco diff</button></div>
  <p className="note">Recorded genuine GPT source · {variant==='attempt_1'?'first proposal':'model revision'}. Historical safety results grant no current approval.</p>
  <p>{proposal.validation.explanation}</p>
  <dl className="properties"><dt>Recorded validation</dt><dd>{proposal.validation.validation_status}</dd><dt>Historical safety</dt><dd>{proposal.verification.physical_safety_status}</dd><dt>Recorded source SHA</dt><dd className="hash">{proposal.validation.proposed_sha256}</dd></dl>
  <div className="actions"><button disabled={busy} onClick={()=>perform(()=>job(prefix+'review/create',{variant},setProgress))}>Review recorded candidate</button></div>
  <form onSubmit={e=>{e.preventDefault();perform(()=>api(prefix+'review?id='+encodeURIComponent(id)));}}><label>Resume review ID<input value={id} onChange={e=>setId(e.target.value)} maxLength={32}/></label><button disabled={busy||id.length!==32}>Load review</button></form>
  {review&&<><strong className="review-status">Current review: {review.status}</strong><code className="hash">{review.review_id}</code><p>{review.explanation}</p><p className="note">Review provenance: {review.provenance.kind||'recorded source'}. Current review source hash: {review.source_sha256}. Source validation: {validation.validation_status}.</p><details><summary>Exact current review diff / source validation</summary><UnifiedDiff source={review.validation.unified_diff}/><pre>{JSON.stringify(review.validation,null,2)}</pre></details>
   {review.reason&&<p role="status">{review.reason}</p>}
   <label className="consent"><input type="checkbox" checked={verifyConsent} onChange={e=>setVerifyConsent(e.target.checked)}/>Approve {family==='arm'?'declared arm scenarios':'A/B/C'} execution in the qualified VM only. This does not apply source.</label>
   <div className="actions"><button disabled={busy||!verifyConsent||!['REVIEWED','BLOCKED'].includes(review.status)} onClick={()=>perform(()=>job(prefix+'review/action',{id:review.review_id,action:'verify',confirmation:'VERIFY IN VM ONLY'},setProgress))}>Verify in isolated VM</button>
   <button disabled={busy||['APPLIED','APPLYING','REVERTING'].includes(review.status)} onClick={()=>perform(()=>job(prefix+'review/action',{id:review.review_id,action:'reject',confirmation:''}))}>Reject candidate</button></div>
   {review.verification&&<><p>Fresh physical result: <strong>{review.verification.physical_safety_status}</strong> · independent {review.verification.verification_execution}</p><details><summary>Fresh {family==='arm'?'arm task':'A/B/C'} measurements</summary><pre>{JSON.stringify(review.verification.scenario_results,null,2)}</pre></details></>}
   <p className="note">Permanent target: {review.apply_target||'robot/approved_controller.py'} (VM-only source). The original host-imported baseline is preserved.</p>
   <label>Separate typed transaction confirmation<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={review.status==='APPLIED'?'REVERT '+review.review_id:'APPLY '+review.source_sha256}/></label>
   <div className="actions"><button disabled={busy||review.status!=='VERIFIED'||confirmation!=='APPLY '+review.source_sha256} onClick={()=>perform(()=>job(prefix+'review/action',{id:review.review_id,action:'apply',confirmation}))}>Apply managed source</button>
   <button disabled={busy||!['APPLIED','APPLYING','REVERTING'].includes(review.status)||confirmation!=='REVERT '+review.review_id} onClick={()=>perform(()=>job(prefix+'review/action',{id:review.review_id,action:'rollback',confirmation}))}>Revert applied source</button></div>
  </>}
  {progress&&<p role="status">{progress}</p>}
 </section>;
}

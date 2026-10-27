// Presentation facts only. This module grants no engineering/execution authority.
export type Activity={title:string;message:string};
export type LocalWork='prepare'|'setup'|'read'|'cancel'|'inspect'|'review'|null;
export const idleActivity:Activity={title:'Idle',message:'No task is running in this view.'};
export function isEmptyWorkspace(p:any){return !p.creation&&!p.shape_specs?.length&&p.world.objects.length===1&&p.world.objects[0].id==='floor'&&p.world.objects[0].geometry==='plane';}
export function errorExplanation(error:string){
 if(/unsupported|firmware|general CAD/i.test(error))return 'This task is outside the supported rover workflow. Your original design is unchanged. Describe a four-wheel rover or use a supported measured rear-motor repair.';
 if(/stale|identity|hash|revision|head|source/i.test(error))return 'The project or saved record no longer matches this request. Your original design is unchanged. Read the current project and prepare a new request if needed; old approval cannot be reused.';
 if(/URLs|file paths|credentials|secrets/i.test(error))return 'Remove file paths, links and credentials from your message. Your original design is unchanged. Never send project secrets.';
 return 'The local action could not be confirmed. Your original design is unchanged. Check the execution and cost records before retrying; no successful design or charge outcome is inferred.';
}
export function physicalComplete(r:any){
 const checks=r?.verification?.checks;
 return !!(r?.proposal&&r.status==='PHYSICAL_PASS'&&r.verification?.status==='PHYSICAL_PASS'&&r.native?.result?.independent_verification?.status==='PASS'&&checks&&Object.keys(checks).length>=8&&Object.values(checks).every(v=>v===true));
}
export function requestPresentation(r:any){
 const base={completed:false,design:r?.proposal?'A proposed design exists. It has not been added to your project.':'No new design has been confirmed.',physics:'Physics has not been verified.',application:'Not applied to your project.'};
 if(r.execution_consumed===true&&['PENDING_APPROVAL','CANCELLED'].includes(r.status))return {...base,title:'Outcome unknown',message:'The consumed execution record conflicts with this status. Check the execution and cost records before retrying.',stage:'Unknown outcome'};
 if(r.status==='PENDING_APPROVAL'){
  if(r.approval_readiness==='EXPIRED')return {...base,title:'Approval window expired',message:'AI has not started. This request is too old to run. Cancel it and prepare a new request.',stage:'Approval required'};
  if(r.approval_readiness==='STALE_SOURCE')return {...base,title:'Request out of date',message:'AI has not started. The implementation changed since preparation. Cancel this request and prepare a new one.',stage:'Approval required'};
  return {...base,title:'Your request is ready. AI has not started.',message:'Choose Build robot to continue. Spending requires your separate confirmation in the native Mac window; reviewing alone does not start AI.',stage:'Approval required'};
 }
 if(['EXECUTION_RESERVED_OR_INTERRUPTED','NATIVE_RESERVED_OR_INTERRUPTED'].includes(r.status))return {...base,title:'Outcome unknown',message:'EMBODY cannot confirm whether the task completed or is still running. Do not retry blindly. Check the execution record; charges may be unknown.',stage:'Unknown outcome'};
 if(r.status==='COMPILED'&&r.proposal)return {...base,title:'Your design is ready to inspect.',message:'The proposed geometry passed validation. Simulation has not been confirmed. Review it before deciding what to do next.',stage:'Ready to review'};
 if(r.status==='PHYSICAL_PASS'&&physicalComplete(r))return {...base,title:'Your proposed design passed verification.',message:'The recorded physics checks and fresh replay passed. Inspect the design; it remains unapplied.',physics:'Physical verification passed for this finite run.',stage:'Completed',completed:true};
 if(r.status==='PHYSICAL_FAIL'&&r.native&&r.verification)return {...base,title:'The robot did not move as expected.',message:'The saved physics run failed one or more checks. View the problem before requesting a separately approved repair.',physics:'Physical verification failed.',stage:'Failed'};
 if(r.status==='CANCELLED')return {...base,title:'Request cancelled',message:'AI did not start under this cancelled request. Opening its workspace did not build a robot.',stage:'Cancelled'};
 if(r.status==='CONSTRUCTION_REJECTED')return {...base,title:'The proposed design was rejected.',message:'Engineering validation found a problem. Your project is unchanged. Inspect the diagnostics; no successful replacement was invented.',stage:'Failed'};
 if(r.status==='FAILED')return {...base,title:'The task stopped.',message:'No completed success is confirmed. Your project is unchanged. Check the saved failure and cost record before any separately approved next attempt.',stage:'Failed'};
 return {...base,title:'Status unavailable',message:'The record does not establish completion or live activity. Check the execution record; do not retry or infer a charge.',stage:'Unknown outcome'};
}
export function activityFor(r:any,work:LocalWork,error:boolean):Activity{
 if(work)return {title:work==='prepare'?'Preparing':work==='setup'?'Setting up workspace':work==='cancel'?'Cancelling':'Reading local record',message:work==='prepare'?'Checking your request locally. AI has not started.':work==='setup'?'Opening a workspace. No robot is being built.':work==='cancel'?'Recording your cancellation. No execution is started here.':'Reading saved information; no new AI or simulation is started.'};
 if(error)return {title:'Needs attention',message:'The local action could not be confirmed. Check the explanation before continuing.'};
 if(!r)return idleActivity;
 const p=requestPresentation(r);
 return {title:p.stage==='Approval required'?'Waiting for authorization':p.stage==='Unknown outcome'?'Unknown outcome':p.stage,message:p.message};
}
export type LocalMessage={text:string;note?:string;requestId?:string};
export function readMessages(key:string):LocalMessage[]{try{const raw=sessionStorage.getItem('embody-conversation:'+key);if(!raw||raw.length>16000)return [];const v=JSON.parse(raw);return Array.isArray(v)&&v.length<=8&&v.every(x=>x&&Object.keys(x).every(k=>['text','note','requestId'].includes(k))&&typeof x.text==='string'&&x.text.length<=1500&&(x.note===undefined||typeof x.note==='string'&&x.note.length<=80)&&(x.requestId===undefined||typeof x.requestId==='string'&&x.requestId.length<=128))?v:[];}catch{return [];}}
export function saveMessages(key:string,values:LocalMessage[]){try{sessionStorage.setItem('embody-conversation:'+key,JSON.stringify(values.slice(-8)));}catch{/* Visible messages still work without storage. */}}

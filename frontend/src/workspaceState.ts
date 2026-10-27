import type {Project,WorldSample} from './engineeringTypes';
import type {ShapePart} from './shapeGeometry';
export type Section='world'|'body'|'shapes'|'circuit'|'firmware'|'assembly'|'ai'|'verification';
export type SavedRun={id:string;title:string;kind:string;proposal:any|null;native:any;verification:any;provenance:any;application_status:string;input_project_sha256:string;source_status?:string};
export type Snapshot={key:string;title:string;project:Project;project_sha256:string;historical:boolean;editable:boolean;runs:SavedRun[];proposals:any[];shape_parts:ShapePart[];catalog:any;electrical:any;action_contracts:any;context:string;circuit_binding:string;firmware_status:string;unavailable?:string[]};
export type WorkspaceData={snapshot:Snapshot;projects:{key:string;title:string}[];policy:any};
type ReviewMemory={sha:string;revision:number;selection:string;component:string;runId:string|null;proposalId:string|null;view:WorkspaceState['view'];index:number;change:any|null;proposals:any[];runs:SavedRun[]};
export type WorkspaceState={memory:Record<string,ReviewMemory>;data:WorkspaceData|null;section:Section;selection:string;component:string;runId:string|null;proposalId:string|null;view:'head'|'proposal'|'simulation'|'change';index:number;change:any|null};
export const initialWorkspace:WorkspaceState={memory:{},data:null,section:'world',selection:'',component:'',runId:null,proposalId:null,view:'head',index:0,change:null};
export function selectedRun(s:WorkspaceState){return s.data?.snapshot.runs.find(r=>r.id===s.runId);}
export function selectedProposal(s:WorkspaceState){const b=s.data?.snapshot;return b?.runs.find(r=>r.proposal?.proposal_id===s.proposalId)?.proposal||b?.proposals.find(p=>p.id===s.proposalId)?.proposal;}
export function representation(s:WorkspaceState):{project:Project;parts:ShapePart[];sample:WorldSample|undefined;label:string}{
 const b=s.data!.snapshot,q=selectedProposal(s),run=selectedRun(s);
 if(s.view==='change'&&s.change)return {project:s.change.proposed_project,parts:s.change.validation.shapes?.parts||[],sample:undefined,label:'LOCAL CHANGE · PROPOSED, NOT APPLIED'};
 if(s.view==='head')return {project:b.project,parts:b.shape_parts,sample:undefined,label:'AUTHORITATIVE PROJECT'};
 if(s.view==='simulation'&&run){const p=run.proposal?.proposed_project||{...b.project,world:run.native.result.world,shape_specs:undefined};return {project:p,parts:run.proposal?.construction.stage_trace.at(-1)?.validation.shapes?.parts||[],sample:run.native.result.samples[s.index],label:'SAVED SIMULATION · '+run.title};}
 if(q)return {project:q.proposed_project,parts:q.construction?.stage_trace.at(-1)?.validation.shapes?.parts||[],sample:undefined,label:'PROPOSED REVISION · NOT APPLIED'};
 return {project:b.project,parts:b.shape_parts,sample:undefined,label:'AUTHORITATIVE PROJECT'};
}
function remember(s:WorkspaceState):ReviewMemory|undefined{const b=s.data?.snapshot;if(!b)return;return {sha:b.project_sha256,revision:b.project.revision,selection:s.selection,component:s.component,runId:s.runId,proposalId:s.proposalId,view:s.view,index:s.index,change:s.change,proposals:b.proposals,runs:b.runs.filter(r=>r.kind==='REQUEST_NATIVE_EVIDENCE')};}
function restore(data:WorkspaceData,m:ReviewMemory|undefined,section:Section,memory:WorkspaceState['memory']):WorkspaceState{
 const b=data.snapshot;
 if(!m||m.sha!==b.project_sha256||m.revision!==b.project.revision)return {...initialWorkspace,data,section,memory};
 const proposals=[...m.proposals.filter(v=>v.proposal?.base_project_sha256===b.project_sha256&&v.proposal?.base_revision===b.project.revision&&!b.proposals.some(p=>p.id===v.id)),...b.proposals];
 const runs=[...m.runs.filter(r=>r.proposal?.base_project_sha256===b.project_sha256&&r.proposal?.base_revision===b.project.revision&&!b.runs.some(v=>v.id===r.id)),...b.runs];
 const nextData={...data,snapshot:{...b,proposals,runs}};
 const next:WorkspaceState={...initialWorkspace,data:nextData,memory,section,selection:m.selection,component:m.component,runId:runs.some(r=>r.id===m.runId)?m.runId:null,proposalId:[...proposals.map(p=>p.id),...runs.map(r=>r.proposal?.proposal_id)].includes(m.proposalId)?m.proposalId:null,view:m.view,index:m.index,change:m.change?.base_project_sha256===b.project_sha256&&m.change?.base_revision===b.project.revision?m.change:null};
 if(next.view==='change'&&!next.change||next.view==='proposal'&&!next.proposalId||next.view==='simulation'&&!next.runId)next.view='head';
 next.index=Math.max(0,Math.min(m.index,(selectedRun(next)?.native.result.samples.length||1)-1));
 if(!representation(next).project.world.objects.some(o=>o.id===next.selection))next.selection='';
 return next;
}
type Action={type:'ai-result';result:any}|{type:'change';change:any}|{type:'discard'}|{type:'open';data:WorkspaceData}|{type:'section';section:Section}|{type:'select';id:string}|{type:'component';id:string}|{type:'run';id:string}|{type:'proposal';id:string}|{type:'head'}|{type:'simulation'}|{type:'index';index:number}|{type:'refresh';data:WorkspaceData};
export function workspaceReducer(s:WorkspaceState,a:Action):WorkspaceState{
 switch(a.type){
  case 'ai-result':{
   const b=s.data?.snapshot,r=a.result,q=r.proposal;
   if(!b||b.key!=='ai-review'||b.historical||!q||r.application_allowed!==false||r.project_sha256!==b.project_sha256||r.project_revision!==b.project.revision||q.base_project_sha256!==b.project_sha256||q.base_revision!==b.project.revision)return s;
   const proposals=[...b.proposals.filter(v=>v.id!==q.proposal_id),{id:q.proposal_id,proposal:q,provenance:{origin:r.origin,parent_origin:r.parent_origin||null}}];
   let runs=b.runs;
   const verified=r.native&&r.verification&&r.native.proposal_id===q.proposal_id&&r.native.result.independent_verification.status==='PASS'&&((r.status==='PHYSICAL_PASS'&&r.verification.status==='PHYSICAL_PASS')||(r.status==='PHYSICAL_FAIL'&&r.verification.status==='PHYSICAL_FAILURE'));
   if(verified){
    const f=r.verification,status=r.status==='PHYSICAL_PASS'?'PASS':'FAIL';
    const run:SavedRun={id:r.request_id,title:(r.origin==='OFFLINE_MOCK_TRANSPORT_NOT_AI'?'Offline mock protocol':'AI request')+' · '+r.request_id.slice(0,8),kind:'REQUEST_NATIVE_EVIDENCE',proposal:q,native:r.native,
     verification:{...f,status,signed_forward_displacement_m:f.measured_signed_forward_displacement_m,required_signed_displacement_m:.005,failure_reasons:status==='FAIL'?['One or more measured native predicates failed.']:[]},
     provenance:{origin:r.origin,authorship:r.origin==='OFFLINE_MOCK_TRANSPORT_NOT_AI'?'Explicit offline transport / fixture-authored plan, not genuine AI.':'Exact provider-authored arguments, preserved with receipts.',api_cost_usd:r.usage?.measured_cost_usd||'0',request_count:r.usage?.requests.length||0},application_status:'PROPOSED_NOT_APPLIED',input_project_sha256:q.resulting_project_sha256};
    runs=[...runs.filter(v=>v.id!==run.id),run];
   }
   const data={...s.data!,snapshot:{...b,proposals,runs}};
   if(r.disposition==='discard')return {...s,data,view:'head',index:0};
   return {...s,data,proposalId:q.proposal_id,runId:verified?r.request_id:null,view:verified?'simulation':'proposal',index:0,selection:q.proposed_project.world.objects.some((o:any)=>o.id===s.selection)?s.selection:''};
  }
  case 'change':{const b=s.data?.snapshot;if(!b||!b.editable||b.historical||b.key!=='current'||a.change.base_project_sha256!==b.project_sha256||a.change.base_revision!==b.project.revision)return s;return {...s,change:a.change,view:'change',index:0};}
  case 'discard':return {...s,change:null,view:'head',index:0};
  case 'open':{const memory={...s.memory};const old=remember(s);if(old&&s.data)memory[s.data.snapshot.key]=old;return restore(a.data,memory[a.data.snapshot.key],s.section,memory);}
  case 'refresh':return restore(a.data,remember(s),s.section,s.memory);
  case 'section':return {...s,section:a.section};
  case 'select':return {...s,selection:a.id};
  case 'component':return {...s,component:a.id};
  case 'head':return {...s,view:'head',selection:s.data?.snapshot.project.world.objects.some(o=>o.id===s.selection)?s.selection:'',index:0};
  case 'run':{
   const r=s.data?.snapshot.runs.find(r=>r.id===a.id);if(!r)return s;
   return {...s,runId:r.id,proposalId:r.proposal?.proposal_id||null,view:'simulation',index:0,selection:r.native.result.world.objects.some((o:any)=>o.id===s.selection)?s.selection:''};
  }
  case 'proposal':{
   const q=s.data?.snapshot.runs.find(r=>r.proposal?.proposal_id===a.id)?.proposal||s.data?.snapshot.proposals.find(p=>p.id===a.id)?.proposal;if(!q)return s;
   return {...s,proposalId:a.id,runId:s.data?.snapshot.runs.find(r=>r.proposal?.proposal_id===a.id)?.id||null,view:'proposal',index:0,selection:q.proposed_project.world.objects.some((o:any)=>o.id===s.selection)?s.selection:''};
  }
  case 'simulation':return selectedRun(s)?{...s,view:'simulation',index:0}:s;
  case 'index':return {...s,index:Math.max(0,Math.min((selectedRun(s)?.native.result.samples.length||1)-1,a.index))};
 }
}

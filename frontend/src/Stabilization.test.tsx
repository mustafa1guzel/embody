// Local component/protocol fixtures only; no genuine model or new physics.
import {beforeEach,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import PropertyEditor from './PropertyEditor';
import AIEngineeringPanel,{requestPresentation} from './AIEngineeringPanel';
import Details from './EngineeringDetails';
import {initialWorkspace,workspaceReducer,representation} from './workspaceState';
import armRaw from '../test/shapebase.json?raw';
import changeRaw from '../test/shapebase_proposal.json?raw';
import roverRaw from '../test/unified.json?raw';
const {call}=vi.hoisted(()=>({call:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args)}));
const arm=JSON.parse(armRaw),q=JSON.parse(changeRaw),rover=JSON.parse(roverRaw);
beforeEach(()=>{call.mockReset();localStorage.clear();sessionStorage.clear();});
const prop=()=>({project:arm.project,sha:arm.identities.project,body:arm.project.world.objects.find((o:any)=>o.id===arm.project.shape_specs[0].body_id),shape:arm.project.shape_specs[0],enabled:true,onProposal:vi.fn()});
const snap=()=>({...rover.snapshot,key:'ai-review',historical:false,editable:false,runs:[],proposals:[]});
const panel=()=>({snapshot:snap(),run:undefined,selection:'',onResult:vi.fn(),onProject:vi.fn(),onRun:vi.fn(),onProposal:vi.fn(),onDiscard:vi.fn()});
const request=(id:string)=>({request_id:id,status:'PENDING_APPROVAL',project_sha256:rover.snapshot.project_sha256,project_revision:0,origin:'NO_MODEL_REQUEST',manifest_sha256:'fixture_hash',manifest:{definition:{}},policy:{max_requests:3,hard_cap_usd:'1.24',maximum_reservation_usd:'1.2288'},task:'Create a four-wheel rover'});

it('does not deliver an abandoned property response after navigation',async()=>{
 let resolve:(v:any)=>void=()=>{};call.mockReturnValue(new Promise(r=>resolve=r));const p=prop(),v=render(<PropertyEditor {...p}/>);
 fireEvent.change(screen.getByRole('spinbutton'),{target:{value:'.42'}});fireEvent.click(screen.getByRole('button',{name:'Review change'}));v.unmount();
 await act(async()=>resolve(q));expect(p.onProposal).not.toHaveBeenCalled();expect(call).toHaveBeenCalledTimes(1);
});
it('retains an unsubmitted numeric tab draft without changing geometry or sending a request',()=>{
 const p=prop(),v=render(<PropertyEditor {...p}/>);fireEvent.change(screen.getByRole('combobox'),{target:{value:'shape:length_m'}});fireEvent.change(screen.getByRole('spinbutton'),{target:{value:'.42'}});v.unmount();render(<PropertyEditor {...p}/>);
 expect(screen.getByRole('spinbutton')).toHaveValue(.42);expect(call).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Cancel edit'}));expect(screen.getByRole('spinbutton')).toHaveValue(p.shape.parameters.length_m);
});
it('restores exact-base review after refresh and a project round trip; changed head invalidates it',()=>{
 const data:any={...rover,snapshot:{...rover.snapshot,key:'current',historical:false,editable:true,project:arm.project,project_sha256:arm.identities.project,runs:[],proposals:[],shape_parts:arm.shapebase.parts}};
 let s=workspaceReducer(initialWorkspace,{type:'open',data});s=workspaceReducer(s,{type:'change',change:q});s=workspaceReducer(s,{type:'select',id:prop().body.id});
 s=workspaceReducer(s,{type:'refresh',data:structuredClone(data)});expect(s.view).toBe('change');
 s=workspaceReducer(s,{type:'open',data:structuredClone(rover)});s=workspaceReducer(s,{type:'open',data:structuredClone(data)});expect(s.view).toBe('change');expect(representation(s).project).toEqual(q.proposed_project);expect(s.selection).toBe(prop().body.id);
 s=workspaceReducer(s,{type:'refresh',data:{...data,snapshot:{...data.snapshot,project_sha256:'new_head'}}});expect(s.view).toBe('head');expect(s.change).toBeNull();
});
it('never converts interrupted native records into a measured FAIL or PASS',()=>{
 const b=snap(),base=rover.snapshot.runs[1];let s=workspaceReducer(initialWorkspace,{type:'open',data:{...rover,snapshot:b}});
 const r={...request('interrupted'),proposal:base.proposal,native:{...base.native,proposal_id:base.proposal.proposal_id},verification:{...base.verification,status:'PHYSICAL_PASS'},status:'NATIVE_RESERVED_OR_INTERRUPTED',application_allowed:false};
 s=workspaceReducer(s,{type:'ai-result',result:r});expect(s.data!.snapshot.runs).toHaveLength(0);expect(s.runId).toBeNull();expect(s.view).toBe('proposal');
});
it('keeps request proposals and recorded native results on refresh without changing the head',()=>{
 const b=snap(),base=rover.snapshot.runs[1],data={...rover,snapshot:b};let s=workspaceReducer(initialWorkspace,{type:'open',data});
 s=workspaceReducer(s,{type:'ai-result',result:{...request('native'),proposal:base.proposal,native:{...base.native,proposal_id:base.proposal.proposal_id},verification:{...base.verification,status:'PHYSICAL_PASS'},status:'PHYSICAL_PASS',origin:'OFFLINE_MOCK_TRANSPORT_NOT_AI',application_allowed:false}});
 s=workspaceReducer(s,{type:'refresh',data:structuredClone(data)});expect(s.view).toBe('simulation');expect(s.data!.snapshot.runs).toHaveLength(1);expect(s.data!.snapshot.project).toEqual(b.project);
});
it('renders exact technical JSON only when opened and removes it when closed',async()=>{
 render(<Details title="Exact evidence" value={{value:.018515946952333998}}/>);expect(document.querySelector('pre')).toBeNull();
 fireEvent.click(screen.getByText('Exact evidence'));await waitFor(()=>expect(document.querySelector('pre')).toHaveTextContent('0.018515946952333998'));
 fireEvent.click(screen.getByText('Exact evidence'));await waitFor(()=>expect(document.querySelector('pre')).toBeNull());
});
it('keeps a natural-language draft on section remount but not on a different head',()=>{
 const p=panel(),v=render(<AIEngineeringPanel {...p}/>);fireEvent.change(screen.getByRole('textbox'),{target:{value:'Create a compact four-wheel rover'}});v.unmount();
 const next=render(<AIEngineeringPanel {...p}/>);expect(screen.getByRole('textbox')).toHaveValue('Create a compact four-wheel rover');next.unmount();
 render(<AIEngineeringPanel {...p} snapshot={{...p.snapshot,project_sha256:'different'}}/>);expect(screen.getByRole('textbox')).toHaveValue('');expect(call).not.toHaveBeenCalled();
});
it('a slow old recovery read cannot overwrite a newly prepared request',async()=>{
 const p=panel();localStorage.setItem('embody-ai-request:ai-review:'+p.snapshot.project_sha256,'old');let finish:(v:any)=>void=()=>{};
 call.mockImplementation((path:string)=>path.endsWith('id=old')?new Promise(r=>finish=r):Promise.resolve(request('new')));
 render(<AIEngineeringPanel {...p}/>);fireEvent.change(screen.getByRole('textbox'),{target:{value:'Create a new four-wheel rover'}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));fireEvent.click(await screen.findByText('Request record'));await screen.findByText(/"request_id": "new"/);
 await act(async()=>finish(request('old')));expect(screen.queryByText(/"request_id": "old"/)).not.toBeInTheDocument();expect(p.onResult).toHaveBeenCalledTimes(1);
});
it('honestly describes expired, consumed, interrupted and failed states',()=>{
 expect(requestPresentation({...request('x'),approval_readiness:'EXPIRED'}).title).toMatch(/expired/);
 expect(requestPresentation({...request('x'),approval_readiness:'STALE_SOURCE'}).title).toMatch(/out of date/);
 expect(requestPresentation({status:'EXECUTION_RESERVED_OR_INTERRUPTED'}).message).toMatch(/Do not retry/);
 expect(requestPresentation({status:'FAILED'}).message).toMatch(/before any separately approved/);
 expect(requestPresentation({status:'invented'}).title).toBe('Status unavailable');
});

// Preserve the existing low-level protocol/recovery coverage under Advanced UI.
function stageLegacy(){const summary=screen.getAllByText('Usage & Safety').find(x=>x.parentElement?.classList.contains('studio-usage'))!;if(!summary.parentElement?.hasAttribute('open'))fireEvent.click(summary);fireEvent.click(screen.getByRole('button',{name:'Send request'}));}

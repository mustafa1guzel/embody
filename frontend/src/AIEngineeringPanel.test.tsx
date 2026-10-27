// Explicit DOM/API protocol fixtures, not a genuine model or physics run.
import {beforeEach,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import AIEngineeringPanel from './AIEngineeringPanel';
import raw from '../test/unified.json?raw';
import {initialWorkspace,representation,workspaceReducer} from './workspaceState';
const {call}=vi.hoisted(()=>({call:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args)}));
const rover=JSON.parse(raw),b={...rover.snapshot,key:'ai-review',historical:false,editable:false,runs:[],proposals:[]};
const result={request_id:'fixture_request',manifest_sha256:'fixture_hash',status:'PENDING_APPROVAL',task:'Create a simple four-wheel rover',project_sha256:b.project_sha256,project_revision:0,manifest_path:'offline fixture path',manifest:{definition:{fixture:true}},policy:{max_requests:3,hard_cap_usd:'1.24',maximum_reservation_usd:'1.2288'},origin:'NO_MODEL_REQUEST',application_allowed:false};
const props=()=>({snapshot:structuredClone(b),run:undefined,selection:'floor',onRun:vi.fn(),onProposal:vi.fn(),onProject:vi.fn(),onResult:vi.fn(),onDiscard:vi.fn()});
beforeEach(()=>{localStorage.clear();call.mockReset();});
it('prepares natural language with exact head/selection and stops visibly at approval',async()=>{
 const p=props();call.mockResolvedValue(structuredClone(result));render(<AIEngineeringPanel {...p}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Your engineering request'}),{target:{value:result.task}});
 stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));
 await screen.findByText('Your request is ready. AI has not started.');expect(call).toHaveBeenCalledWith('ai-engineering/prepare',{workflow:'assembly',task:result.task,expected_sha256:b.project_sha256,expected_revision:0,selection:'floor',baseline_request_id:null,run_options:{profile:'expanded',hard_cap_usd:'2.50',native_preview:false}});
 fireEvent.click(screen.getByText('Advanced Details · execution & approval'));expect(screen.getByText(/No model request made/)).toBeVisible();expect(screen.getByText(/hard cap \$1.24/)).toBeVisible();
 expect(call.mock.calls.filter(([p])=>p==='ai-engineering/prepare')).toHaveLength(1);expect(p.onResult).toHaveBeenCalledWith(result);
});
it('blocks duplicate submission while preparing and cancels only pending scope',async()=>{
 let finish:(v:any)=>void=()=>{};call.mockReturnValueOnce(new Promise(r=>finish=r));render(<AIEngineeringPanel {...props()}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:result.task}});const form=screen.getByRole('textbox').closest('form')!;
 stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));expect(call).toHaveBeenCalledTimes(1);
 await act(async()=>finish(result));call.mockResolvedValue({...result,status:'CANCELLED'});
 fireEvent.click(screen.getByRole('button',{name:'Cancel unstarted request'}));await screen.findByText('Request cancelled');expect(screen.queryByRole('button',{name:'Cancel unstarted request'})).not.toBeInTheDocument();
});
it('shows authentic backend rejection without fabricated correction',async()=>{
 call.mockRejectedValue(new Error('Unsupported request: firmware is unavailable'));render(<AIEngineeringPanel {...props()}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Run firmware for my rover'}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));
 const err=await screen.findByRole('alert');fireEvent.click(screen.getByText('Error details'));await waitFor(()=>expect(err).toHaveTextContent('firmware is unavailable'));expect(screen.queryByTestId('ai-request-state')).not.toBeInTheDocument();
});
it('distinguishes a mocked compiled proposal, native unavailable and retain/discard review',async()=>{
 const p=props(),q=rover.snapshot.runs[0].proposal;
 const value={...result,status:'COMPILED',origin:'OFFLINE_MOCK_TRANSPORT_NOT_AI',proposal:q,approval_message:'Separate approval required'};
 call.mockResolvedValue(value);render(<AIEngineeringPanel {...p}/>);fireEvent.change(screen.getByRole('textbox'),{target:{value:result.task}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));
 await screen.findAllByText(/OFFLINE MOCK TRANSPORT/);fireEvent.click(screen.getByText('Advanced Details · execution & approval'));expect(screen.getByText(/NOT VERIFIED/)).toBeVisible();
 expect(screen.getByRole('button',{name:'Native verification · separate approved runner'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Preview proposed geometry'}));expect(p.onProposal).toHaveBeenCalledWith(q.proposal_id);
 call.mockResolvedValue({...value,disposition:'discard'});fireEvent.click(screen.getByRole('button',{name:'Discard review view'}));await screen.findByText(/Review discard recorded/);expect(p.onDiscard).toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Preview proposed geometry'}));expect(p.onProposal).toHaveBeenCalledTimes(2);
 expect(call.mock.calls.some(([path])=>/execute|apply|native/.test(path))).toBe(false);
});
it('never injects a late result into a switched project',async()=>{
 let finish:(v:any)=>void=()=>{};call.mockReturnValueOnce(new Promise(r=>finish=r));const p=props();const view=render(<AIEngineeringPanel {...p}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:result.task}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));view.unmount();
 await act(async()=>finish(result));expect(p.onResult).not.toHaveBeenCalled();
});
it('opens saved real failure/repair separately with their actual costs and operations',()=>{
 const p={...props(),snapshot:rover.snapshot,run:rover.snapshot.runs[1]};render(<AIEngineeringPanel {...p}/>);
 expect(screen.getByText(/separate genuine GPT sessions/)).toBeVisible();expect(screen.getByTestId('unified-cost')).toHaveTextContent('0.0190800');
 fireEvent.click(screen.getByRole('button',{name:'Inspect original failure'}));expect(p.onRun).toHaveBeenCalledWith('phase18e5');
 fireEvent.click(screen.getByRole('button',{name:'Inspect genuine repair'}));expect(p.onRun).toHaveBeenCalledWith('phase18e7');expect(call).not.toHaveBeenCalled();
});
it('reducer binds compiled/native result to exact project, retains head and never treats compile as physics',()=>{
 let s=workspaceReducer(initialWorkspace,{type:'open',data:{...rover,snapshot:b}});const before=JSON.stringify(s.data?.snapshot.project);
 const q=rover.snapshot.runs[0].proposal;
 expect(workspaceReducer(s,{type:'ai-result',result:{...result,project_sha256:'bad',proposal:q}})).toBe(s);
 s=workspaceReducer(s,{type:'ai-result',result:{...result,proposal:q}});expect(s.view).toBe('proposal');expect(representation(s).project.shape_specs).toHaveLength(9);expect(s.runId).toBeNull();
 expect(JSON.stringify(s.data?.snapshot.project)).toBe(before);
 s=workspaceReducer(s,{type:'open',data:rover});expect(s.proposalId).toBeNull();
 expect(workspaceReducer(s,{type:'ai-result',result:{...result,proposal:q}})).toBe(s);
});
it('handles missing saved request with an explicit read error and no replacement',async()=>{
 localStorage.setItem('embody-ai-request:ai-review:'+b.project_sha256,'missing');call.mockRejectedValue(new Error('Stored identity mismatch'));
 render(<AIEngineeringPanel {...props()}/>);await screen.findByRole('alert');fireEvent.click(screen.getByText('Error details'));await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Stored identity mismatch'));
 expect(screen.queryByText('Construction compiled')).not.toBeInTheDocument();
});

it('explicitly separates a proposal-only selection from a new EMPTY-head assembly request',async()=>{
 const p={...props(),selection:'proposal-only-wheel'};call.mockResolvedValue(structuredClone(result));render(<AIEngineeringPanel {...p}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Your engineering request'}),{target:{value:result.task}});stageLegacy();
 expect(screen.getByText(/selected part belongs to a proposal/)).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Prepare approval request'}));
 await screen.findByText('Your request is ready. AI has not started.');expect(call).toHaveBeenCalledWith('ai-engineering/prepare',expect.objectContaining({selection:'',expected_sha256:b.project_sha256}));
});

// Preserve the existing low-level protocol/recovery coverage under Advanced UI.
function stageLegacy(){const summary=screen.getAllByText('Usage & Safety').find(x=>x.parentElement?.classList.contains('studio-usage'))!;if(!summary.parentElement?.hasAttribute('open'))fireEvent.click(summary);fireEvent.click(screen.getByRole('button',{name:'Send request'}));}

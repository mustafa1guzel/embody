// Controlled API protocol fixtures only; no provider, native dialog or dynamics.
import {beforeEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import AIEngineeringPanel from './AIEngineeringPanel';
import RampPanel from './RampPanel';
import raw from '../test/unified.json?raw';
const {call,runJob}=vi.hoisted(()=>({call:vi.fn(),runJob:vi.fn()}));vi.mock('./api',()=>({api:(...a:unknown[])=>call(...a),job:(...a:unknown[])=>runJob(...a)}));
const snapshot={...JSON.parse(raw).snapshot,key:'ai-review',historical:false,editable:false,runs:[],proposals:[]};
const goal='Build me a simple four-wheel robot car.';
const request={request_id:'fixture-request',project_sha256:snapshot.project_sha256,project_revision:0,status:'PENDING_APPROVAL',task:goal,application_allowed:false,origin:'NO_MODEL_REQUEST',policy:{hard_cap_usd:'2.50',maximum_reservation_usd:'2.3538',max_requests:3,native_previews:0},manifest:{definition:{}},manifest_path:'fixture'};
const quote={review_id:'fixture-review',task:goal,policy:request.policy,native_confirmation_supported:true};
const props=()=>({snapshot,selection:'',run:undefined,onRun:vi.fn(),onProposal:vi.fn(),onProject:vi.fn(),onResult:vi.fn(),onDiscard:vi.fn()});
beforeEach(()=>{localStorage.clear();call.mockReset();runJob.mockReset();HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};});
it('one Build robot prepares and reviews the exact request without starting paid execution',async()=>{
 call.mockImplementation(async(p:string)=>p==='ai-engineering/prepare'?request:p==='ai-engineering/review-run'?quote:{active:false,stage:'NOT_STARTED'});
 render(<AIEngineeringPanel {...props()}/>);expect(screen.getByText('Usage & Safety').parentElement).not.toHaveAttribute('open');
 expect(screen.getByLabelText('AI spending limit USD')).not.toBeVisible();
 fireEvent.change(screen.getByRole('textbox',{name:'Your engineering request'}),{target:{value:goal}});fireEvent.click(screen.getByRole('button',{name:'Build robot'}));
 const modal=await screen.findByRole('dialog',{name:'Review AI run'});expect(within(modal).getByText('$2.50 USD')).toBeVisible();
 expect(within(modal).queryByText(/2.3538/)).not.toBeVisible();expect(call.mock.calls.filter(([p])=>p==='ai-engineering/prepare')).toHaveLength(1);
 expect(call.mock.calls.some(([p])=>p==='ai-engineering/start-building')).toBe(false);expect(within(modal).getByRole('button',{name:'Start building'})).toBeEnabled();
});
it('normal Build carries the unchanged goal into a checked new project before preparation',async()=>{
 const p={...props(),snapshot:{...snapshot,key:'current'},onGuidedProject:vi.fn()};call.mockResolvedValue({project_key:'ai-review',project_sha256:'expected-head',revision:0});render(<AIEngineeringPanel {...p}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:goal}});fireEvent.click(screen.getByRole('button',{name:'Build robot'}));await waitFor(()=>expect(p.onGuidedProject).toHaveBeenCalledWith('ai-review','expected-head',goal,true));expect(call).toHaveBeenCalledTimes(1);
});
it('Add ramp previews real backend proposal data and tests only after an explicit second action',async()=>{
 const review={id:'fixture-ramp-review',parameters:{angle_deg:5,length_m:1,width_m:.4,thickness_m:.04,friction:.9},status:'NOT_RUN',origin:'DEVELOPER_AUTHORED_REFERENCE_NOT_AI'};call.mockResolvedValue(review);const view=vi.fn();const r=render(<RampPanel review={null} onView={view} onActivity={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add ramp'}));await waitFor(()=>expect(view).toHaveBeenCalledWith(review));expect(runJob).not.toHaveBeenCalled();
 r.rerender(<RampPanel review={review} onView={view} onActivity={vi.fn()}/>);expect(screen.getByText('Physics has not started.')).toBeVisible();
 const measured={...review,status:'FAIL',result:{measurements:{outcome:'MOVED_DOWNHILL',signed_progress_m:-.1,height_change_m:-.05,wheel_ramp_pair_observations:{wheel:4},unexpected_contacts:[]},native:{independent_verification:{status:'PASS'}}}};runJob.mockResolvedValue(measured);
 fireEvent.click(screen.getByRole('button',{name:'Test robot'}));await waitFor(()=>expect(view).toHaveBeenCalledWith(measured,200));r.rerender(<RampPanel review={measured} onView={view} onActivity={vi.fn()}/>);
 expect(screen.getByTestId('ramp-verdict')).toHaveTextContent('Moved downhill · FAIL');expect(screen.getByTestId('ramp-verdict')).toHaveTextContent('rolling versus tire slip is unresolved');expect(screen.queryByRole('button',{name:'Test robot'})).toBeNull();
});
it('changed ramp drafts cannot reuse a saved proposal for a new test',()=>{
 const review={id:'fixture-review',parameters:{angle_deg:5,length_m:1,width_m:.4,thickness_m:.04,friction:.9},status:'NOT_RUN'};render(<RampPanel review={review} onView={vi.fn()} onActivity={vi.fn()}/>);
 fireEvent.change(screen.getByRole('slider',{name:'Ramp angle degrees'}),{target:{value:'30'}});expect(screen.getByRole('button',{name:'Test robot'})).toBeDisabled();expect(runJob).not.toHaveBeenCalled();
});

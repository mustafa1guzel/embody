// Controlled API/approval fixtures only. No native dialog, paid model or physics.
import {expect,it,vi,beforeEach} from 'vitest';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import StudioRunControls,{executionActivity} from './StudioRunControls';
const {call}=vi.hoisted(()=>({call:vi.fn()}));vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args)}));
const request={request_id:'request-fixture',status:'PENDING_APPROVAL'};
const quote={review_id:'exact-review-fixture',task:'Build my four-wheel rover',native_confirmation_supported:true,policy:{max_requests:3,hard_cap_usd:'2.50',maximum_reservation_usd:'2.3538',native_previews:0}};
beforeEach(()=>{call.mockReset();vi.stubGlobal('HTMLDialogElement',HTMLDialogElement);HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};});
it('reviews locally and sends only the review ID, never a browser approval record',async()=>{
 const refresh=vi.fn();call.mockImplementation(async(p:string)=>p.includes('execution-status')?{active:false,stage:'NOT_STARTED'}:p.endsWith('review-run')?quote:{job_id:'actual-fixture-job'});
 render(<StudioRunControls request={request} onRefresh={refresh} onActivity={vi.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Build robot'}));await screen.findByRole('dialog',{name:'Review AI run'});
 expect(call.mock.calls.some(([p])=>p.endsWith('start-building'))).toBe(false);expect(screen.getByText(/Start building opens a Mac confirmation window/)).toBeVisible();expect(screen.getByText(/Geometry review only/)).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Start building'}));await waitFor(()=>expect(call).toHaveBeenCalledWith('ai-engineering/start-building',{review_id:quote.review_id}));expect(call.mock.calls.filter(([p])=>p.endsWith('start-building'))).toHaveLength(1);
});
it('explains unavailable native authorization and cannot issue an execution request',async()=>{
 call.mockImplementation(async(p:string)=>p.includes('execution-status')?{active:false,stage:'NOT_STARTED'}:{...quote,native_confirmation_supported:false});render(<StudioRunControls request={request} onRefresh={vi.fn()} onActivity={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Build robot'}));await screen.findByRole('dialog');expect(screen.getByRole('button',{name:'Start building'})).toBeDisabled();expect(screen.getByRole('alert')).toHaveTextContent('Execution cannot start');expect(call.mock.calls.some(([p])=>p.endsWith('start-building'))).toBe(false);
});
it('does not infer live work from a stored reservation and does not retry uncertain starts',async()=>{
 expect(executionActivity({active:false,stage:'UNKNOWN_OUTCOME'})?.title).toBe('Unknown outcome');expect(executionActivity({active:false,stage:'model_request_started'})).toBeNull();expect(executionActivity({active:true,stage:'model_request_started'})?.title).toBe('Waiting for AI response');
 call.mockImplementation(async(p:string)=>{if(p.includes('execution-status'))return {active:false,stage:'NOT_STARTED'};if(p.endsWith('review-run'))return quote;throw new Error('Transport result unknown');});
 render(<StudioRunControls request={request} onRefresh={vi.fn()} onActivity={vi.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Build robot'}));await screen.findByRole('dialog');fireEvent.click(screen.getByRole('button',{name:'Start building'}));await screen.findByRole('alert');expect(call.mock.calls.filter(([p])=>p.endsWith('start-building'))).toHaveLength(1);
});

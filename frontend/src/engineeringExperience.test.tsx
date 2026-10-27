// Presentation/protocol fixtures, not provider output or fabricated physics.
import {beforeEach,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {activityFor,physicalComplete,requestPresentation,readMessages,saveMessages,errorExplanation,isEmptyWorkspace} from './engineeringExperience';
import AIEngineeringPanel from './AIEngineeringPanel';
import raw from '../test/unified.json?raw';
const {call}=vi.hoisted(()=>({call:vi.fn()}));vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args)}));
const saved=JSON.parse(raw),b={...saved.snapshot,key:'current',historical:false,editable:true,runs:[],proposals:[]};
const props=()=>({snapshot:b,run:undefined,selection:'',onRun:vi.fn(),onProposal:vi.fn(),onProject:vi.fn(),onResult:vi.fn(),onDiscard:vi.fn(),onGuidedProject:vi.fn(),onActivity:vi.fn()});
const task='Build me a four-wheel robot car.';
beforeEach(()=>{localStorage.clear();sessionStorage.clear();call.mockReset();});
it('stages an actual user message with honest local guidance and no API request',()=>{
 render(<AIEngineeringPanel {...props()}/>);fireEvent.change(screen.getByRole('textbox'),{target:{value:task}});stageLegacy();
 expect(within(screen.getByRole('list',{name:'Engineering conversation'})).getByText(task)).toBeVisible();expect(screen.getByText(/No AI has started and no new robot exists/)).toBeVisible();expect(screen.queryByLabelText('Verified proposal')).toBeNull();expect(call).not.toHaveBeenCalled();
});
it('carries only the original task to the exact server-confirmed empty workspace',async()=>{
 const p=props();call.mockResolvedValue({project_key:'ai-review',project_sha256:'target',revision:0});render(<AIEngineeringPanel {...p}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:task}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Set up robot workspace'}));
 await waitFor(()=>expect(p.onGuidedProject).toHaveBeenCalledWith('ai-review','target',task));expect(call).toHaveBeenCalledExactlyOnceWith('ai-engineering/new-project',{});expect(p.onResult).not.toHaveBeenCalled();
});
it('rejects a nonempty setup response and suppresses a setup response after leaving',async()=>{
 const p=props();call.mockResolvedValue({project_key:'ai-review',project_sha256:'target',revision:1});const v=render(<AIEngineeringPanel {...p}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:task}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Set up robot workspace'}));await screen.findByRole('alert');expect(p.onGuidedProject).not.toHaveBeenCalled();v.unmount();
 let finish:(v:any)=>void=()=>{};call.mockReturnValue(new Promise(r=>finish=r));const second=render(<AIEngineeringPanel {...p}/>);fireEvent.click(screen.getByRole('button',{name:'Set up robot workspace'}));second.unmount();await act(async()=>finish({project_key:'ai-review',project_sha256:'target',revision:0}));expect(p.onGuidedProject).not.toHaveBeenCalled();
});
it('preserves the visible prompt only on its explicit matching handoff and does not prepare automatically',()=>{
 const p=props(),q={...b,key:'ai-review',editable:false,project_sha256:'target'};const v=render(<AIEngineeringPanel {...p} snapshot={q} guidedTask={{text:task,projectSha:'target'}}/>);
 expect(screen.getByRole('textbox')).toHaveValue(task);expect(screen.getByText(/Your workspace is ready. No robot has been created yet/)).toBeVisible();expect(screen.getByRole('button',{name:'Prepare approval request'})).toBeEnabled();expect(call).not.toHaveBeenCalled();v.unmount();
 render(<AIEngineeringPanel {...p} snapshot={{...q,project_sha256:'different'}} guidedTask={{text:task,projectSha:'target'}}/>);expect(screen.getByRole('textbox')).toHaveValue('');expect(screen.queryByText(task)).toBeNull();
});
it.each(['PENDING_APPROVAL','COMPILED','PHYSICAL_FAIL','FAILED','CANCELLED','EXECUTION_RESERVED_OR_INTERRUPTED','NATIVE_RESERVED_OR_INTERRUPTED','RUNNING','unrecognized'])('never completes a request from status %s alone',status=>{
 const r={status,proposal:status==='COMPILED'?{}:undefined};expect(physicalComplete(r)).toBe(false);expect(requestPresentation(r).completed).toBe(false);expect(activityFor(r,null,false).title).not.toBe('Running');
});
it('requires actual complete physics and fresh replay evidence for a completion check',()=>{
 const r={status:'PHYSICAL_PASS',proposal:{},verification:{status:'PHYSICAL_PASS',checks:Object.fromEntries(Array.from({length:8},(_,i)=>['check'+i,true]))},native:{result:{independent_verification:{status:'PASS'}}}};
 expect(physicalComplete(r)).toBe(true);expect(requestPresentation(r).completed).toBe(true);expect(requestPresentation(r).application).toMatch(/Not applied/);
 expect(physicalComplete({...r,native:undefined})).toBe(false);expect(physicalComplete({...r,verification:{...r.verification,checks:{...r.verification.checks,check3:false}}})).toBe(false);expect(physicalComplete({...r,verification:{...r.verification,checks:{}}})).toBe(false);
});
it('never describes an execution reservation, old approval or contradictory consumed status as live work',()=>{
 for(const status of ['EXECUTION_RESERVED_OR_INTERRUPTED','NATIVE_RESERVED_OR_INTERRUPTED','PENDING_APPROVAL','CANCELLED'])expect(requestPresentation({status,execution_consumed:true}).stage).toBe('Unknown outcome');
 expect(activityFor(null,'prepare',false).message).toMatch(/locally. AI has not started/);expect(activityFor(null,'setup',false).message).toMatch(/No robot is being built/);expect(activityFor(null,null,false).title).toBe('Idle');
});
it('bounds local visible history and rejects malformed stored data without granting authority',()=>{
 saveMessages('exact-head',Array.from({length:10},(_,i)=>({text:'Local message '+i})));expect(readMessages('exact-head')).toHaveLength(8);expect(readMessages('another-head')).toEqual([]);
 sessionStorage.setItem('embody-conversation:exact-head',JSON.stringify([{text:'fake',authority:true}]));expect(readMessages('exact-head')).toEqual([]);
});
it('explains common failures without inventing successful construction or uncharged provider execution',()=>{
 expect(errorExplanation('Unsupported request: firmware is unavailable')).toMatch(/outside the supported rover/);
 expect(errorExplanation('Stale project revision/hash')).toMatch(/old approval cannot be reused/);
 expect(errorExplanation('Do not include URLs, file paths or credentials')).toMatch(/Never send project secrets/);
 expect(errorExplanation('Provider transport outcome unknown')).toMatch(/cost records before retrying/);
});
it('calls only the actual bare floor workspace empty, never a lone real body or generated design',()=>{
 const p=structuredClone(b.project);expect(isEmptyWorkspace(p)).toBe(true);
 expect(isEmptyWorkspace({...p,world:{...p.world,objects:[{...p.world.objects[0],id:'real_body',geometry:'box'}]}})).toBe(false);
 expect(isEmptyWorkspace({...p,creation:{family:'sensor_barrier'}})).toBe(false);
 expect(isEmptyWorkspace({...p,shape_specs:[{}]})).toBe(false);
});
it('refuses to promise or reset a populated review workspace',()=>{
 const p=props();render(<AIEngineeringPanel {...p} snapshot={{...b,key:'ai-review',project:{...b.project,revision:1}}}/>);fireEvent.change(screen.getByRole('textbox'),{target:{value:task}});stageLegacy();expect(screen.getByText(/It cannot be reset here/)).toBeVisible();expect(screen.getByRole('button',{name:'Set up robot workspace'})).toBeDisabled();expect(screen.queryByRole('button',{name:'Prepare approval request'})).toBeNull();expect(call).not.toHaveBeenCalled();
});

// Preserve the existing low-level protocol/recovery coverage under Advanced UI.
function stageLegacy(){const summary=screen.getAllByText('Usage & Safety').find(x=>x.parentElement?.classList.contains('studio-usage'))!;if(!summary.parentElement?.hasAttribute('open'))fireEvent.click(summary);fireEvent.click(screen.getByRole('button',{name:'Send request'}));}

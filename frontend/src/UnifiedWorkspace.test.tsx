import {beforeEach,expect,it,vi} from 'vitest';
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import raw from '../test/unified.json?raw';
import engineeringRaw from '../test/engineering.json?raw';
import UnifiedWorkspace from './UnifiedWorkspace';
import {initialWorkspace,representation,selectedRun,workspaceReducer} from './workspaceState';
const {call}=vi.hoisted(()=>({call:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args)}));
vi.mock('./WorldViewport',()=>({default:(p:any)=><div data-testid="unified-dom-canvas" data-selection={p.selection} data-world={p.world.id} data-time={p.sample?.time_s??'static'}><button onClick={()=>p.onSelect('body_wheel_rear_left')}>DOM canvas wheel selection fixture</button></div>}));
vi.mock('./EngineeringWorkspace',()=>({default:()=> <p>Existing validated editors DOM fixture</p>}));
const rover=JSON.parse(raw),boot=JSON.parse(engineeringRaw);
const current={...rover,snapshot:{...rover.snapshot,key:'current',title:boot.project.id,project:boot.project,project_sha256:boot.identities.project,historical:false,editable:true,runs:[],proposals:[],shape_parts:[],catalog:boot.catalog,electrical:boot.electrical,action_contracts:boot.action_contracts}};
beforeEach(()=>{localStorage.clear();call.mockReset();call.mockImplementation(async(path:string)=>{if(path==='workspace?project=current')return structuredClone(current);if(path==='workspace?project=rover')return structuredClone(rover);if(path==='engineering/context')return {identities:boot.identities};throw new Error('Unexpected DOM fixture request '+path);});});
async function openRover(){render(<UnifiedWorkspace/>);await screen.findByTestId('unified-project-identity');fireEvent.change(screen.getByRole('combobox',{name:'Open engineering project'}),{target:{value:'rover'}});await waitFor(()=>expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-sha256',rover.snapshot.project_sha256));fireEvent.click(screen.getByRole('button',{name:'Simulate'}));}
it('opens actual backend head and keeps identity/selection across all sections without mutations',async()=>{
 render(<UnifiedWorkspace/>);const identity=await screen.findByTestId('unified-project-identity');expect(identity).toHaveAttribute('data-project',boot.project.id);fireEvent.click(screen.getByText('Advanced Tools',{exact:true}));
 fireEvent.click(await screen.findByRole('button',{name:'Inspect body floor'}));
 for(const name of ['Bodies / BODYBASE','Shapes / SHAPEBASE','Circuit / CIRCUITBASE','Firmware / Code','Assembly','AI engineering','Verification','World / WORLDBASE']){
  fireEvent.click(within(screen.getByRole('navigation',{name:'Project engineering sections'})).getByRole('button',{name}));expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-project',boot.project.id);expect(screen.getByTestId('unified-dom-canvas')).toHaveAttribute('data-selection','floor');
 }
 expect(call.mock.calls.every(x=>x.length===1)).toBe(true);
});
it('synchronizes selected proposed wheel, typed dimensions, mass, mount, joint and actuator',async()=>{
 await openRover();fireEvent.click(screen.getByRole('button',{name:/GPT physical repair · Phase 18E.7 PASS/}));fireEvent.click(screen.getByRole('button',{name:'DOM canvas wheel selection fixture'}));
 const inspector=screen.getByTestId('unified-inspector');fireEvent.click(within(inspector).getByText('Advanced Details'));await waitFor(()=>expect(inspector).toHaveTextContent('body_wheel_rear_left'));expect(inspector).toHaveTextContent('body_wheel_rear_left');expect(inspector).toHaveTextContent('wheel_rear_left');expect(inspector).toHaveTextContent('35 mm');expect(inspector).toHaveTextContent('hinge_rear_left');expect(inspector).toHaveTextContent('-0.012 N*m');expect(inspector).toHaveAttribute('data-body-id','body_wheel_rear_left');
 fireEvent.click(screen.getByText('Advanced Tools',{exact:true}));fireEvent.click(screen.getByRole('button',{name:'Shapes / SHAPEBASE'}));expect(screen.getByTestId('unified-dom-canvas')).toHaveAttribute('data-selection','body_wheel_rear_left');expect(screen.getByTestId('workspace-representation')).toHaveTextContent('SAVED SIMULATION');
});
it('keeps genuine original failure and subsequent repair provenance separate; never applies either',async()=>{
 await openRover();fireEvent.click(screen.getByRole('button',{name:/Original GPT rover · Phase 18E.5 FAIL/}));expect(screen.getByTestId('unified-verdict')).toHaveTextContent('-0.018516');expect(screen.getByTestId('unified-verdict')).toHaveTextContent('backwards');
 fireEvent.click(screen.getByRole('button',{name:'AI Assistant'}));expect(screen.getByTestId('unified-cost')).toHaveTextContent('0.1586060');
 fireEvent.click(screen.getByRole('button',{name:'Properties'}));fireEvent.click(screen.getByRole('button',{name:/GPT physical repair · Phase 18E.7 PASS/}));expect(screen.getByTestId('unified-verdict')).toHaveTextContent('+0.018516');fireEvent.click(screen.getByRole('button',{name:'AI Assistant'}));expect(screen.getByTestId('unified-cost')).toHaveTextContent('0.0190800');fireEvent.click(screen.getByText('Original request & authorship',{exact:true}));expect(screen.getAllByText(/Only the new supplied operations/).some(x=>x.tagName==='P')).toBe(true);
 fireEvent.click(screen.getByText('Advanced Tools',{exact:true}));fireEvent.click(screen.getByRole('navigation',{name:'Project engineering sections'}).querySelector('[aria-label=Assembly]')!);expect(screen.getByRole('button',{name:'Apply proposal · no application authority'})).toBeDisabled();expect(screen.getByTestId('unified-proposal-status')).toHaveTextContent('PROPOSED_NOT_APPLIED');
 fireEvent.click(screen.getByRole('button',{name:'Proposed revision'}));expect(screen.getByTestId('unified-dom-canvas')).toHaveAttribute('data-time','static');
 fireEvent.click(screen.getByRole('button',{name:'Authoritative project'}));expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-revision','0');expect(screen.queryByRole('button',{name:'Inspect body body_chassis'})).not.toBeInTheDocument();
 expect(call.mock.calls.every(x=>x.length===1)).toBe(true);
});
it('scrubs and plays actual saved-state fixture timestamps; pause freezes and head view disables playback',async()=>{
 await openRover();fireEvent.click(screen.getByRole('button',{name:/GPT physical repair · Phase 18E.7 PASS/}));fireEvent.change(screen.getByRole('slider',{name:'Unified measured timeline'}),{target:{value:'2'}});expect(screen.getByTestId('unified-dom-canvas')).toHaveAttribute('data-time',String(rover.snapshot.runs[1].native.result.samples[2].time_s));
 fireEvent.click(screen.getByRole('button',{name:'Replay from start'}));expect(screen.getByTestId('unified-measured-time')).toHaveTextContent('0.000');
 let cb:FrameRequestCallback|undefined;vi.stubGlobal('requestAnimationFrame',vi.fn((f:FrameRequestCallback)=>{cb=f;return 1;}));vi.stubGlobal('cancelAnimationFrame',vi.fn());vi.spyOn(performance,'now').mockReturnValue(0);
 fireEvent.click(screen.getByRole('button',{name:'Play saved simulation'}));act(()=>cb?.(10));expect(screen.getByTestId('unified-measured-time')).toHaveTextContent('0.005');fireEvent.click(screen.getByRole('button',{name:'Pause saved simulation'}));expect(cancelAnimationFrame).toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Authoritative project'}));expect(screen.getByRole('button',{name:'Play saved simulation'})).toBeDisabled();
});
it('discloses absent run, electrical binding and untrusted firmware; local inspection is labelled',async()=>{
 render(<UnifiedWorkspace/>);await screen.findByTestId('unified-project-identity');fireEvent.click(screen.getByRole('button',{name:'Simulate'}));expect(screen.getByText(/No saved simulation is available/)).toBeInTheDocument();fireEvent.click(screen.getByText('Advanced Tools',{exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Circuit / CIRCUITBASE'}));expect(screen.getByText(/No battery, motor-driver/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Firmware / Code'}));expect(screen.getByText(/Untrusted code execution remains blocked/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'AI Assistant'}));fireEvent.click(screen.getByText('Context & engineering limits',{exact:true}));fireEvent.click(screen.getByRole('button',{name:'Inspect current project locally'}));await screen.findByText('Deterministic backend inspection; no model response.');expect(screen.queryByText('GENUINE_PROVIDER_RESPONSE')).not.toBeInTheDocument();
});
it('retains loaded state with a visible error when another project cannot be read; no replacement',async()=>{
 render(<UnifiedWorkspace/>);await screen.findByTestId('unified-project-identity');call.mockRejectedValueOnce(new Error('Historical evidence bytes differ'));
 fireEvent.change(screen.getByRole('combobox',{name:'Open engineering project'}),{target:{value:'rover'}});const alert=await screen.findByRole('alert');fireEvent.click(screen.getByText('Read error details'));await waitFor(()=>expect(alert).toHaveTextContent('Historical evidence bytes differ'));expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-project',boot.project.id);expect(screen.queryByRole('button',{name:/GPT physical repair · Phase 18E.7 PASS/})).not.toBeInTheDocument();
});
it('reducer refuses unknown proposal/run IDs, preserves input data, resets incompatible selections on project change',()=>{
 const data=structuredClone(rover);let s=workspaceReducer(initialWorkspace,{type:'open',data});const before=JSON.stringify(data);
 expect(workspaceReducer(s,{type:'run',id:'not-a-run'})).toBe(s);expect(workspaceReducer(s,{type:'proposal',id:'not-a-proposal'})).toBe(s);
 s=workspaceReducer(s,{type:'run',id:'phase18e7'});s=workspaceReducer(s,{type:'select',id:'body_wheel_rear_left'});s=workspaceReducer(s,{type:'section',section:'ai'});expect(representation(s).project.shape_specs).toHaveLength(9);expect(selectedRun(s)?.verification.status).toBe('PASS');
 s=workspaceReducer(s,{type:'head'});expect(representation(s).project.shape_specs).toBeUndefined();expect(s.selection).toBe('');expect(JSON.stringify(data)).toBe(before);
 s=workspaceReducer(s,{type:'open',data:structuredClone(current)});expect(s.proposalId).toBeNull();expect(s.runId).toBeNull();expect(s.section).toBe('ai');
});
it('collapses, restores and keyboard-resizes panels without losing current project or selection',async()=>{
 render(<UnifiedWorkspace/>);await screen.findByTestId('unified-project-identity');fireEvent.click(screen.getByRole('button',{name:'Inspect body floor'}));
 const separator=screen.getByRole('separator',{name:'Resize left workspace panel'});const old=Number(separator.getAttribute('aria-valuenow'));fireEvent.keyDown(separator,{key:'ArrowRight'});expect(Number(separator.getAttribute('aria-valuenow'))).toBe(old+16);
 fireEvent.click(screen.getByRole('button',{name:'Toggle project sidebar'}));expect(screen.queryByRole('navigation',{name:'Studio actions'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Toggle project sidebar'}));expect(screen.getByRole('button',{name:'Inspect body floor'})).toHaveAttribute('aria-pressed','true');
 fireEvent.click(screen.getByRole('button',{name:'Focus canvas'}));expect(screen.queryByRole('separator')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Toggle inspector'}));expect(screen.getByTestId('unified-inspector')).toBeVisible();expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-project',boot.project.id);
});
it('groups eight retained tools below four primary actions and shows playback only in Simulate',async()=>{
 await openRover();expect(within(screen.getByRole('navigation',{name:'Studio actions'})).getAllByRole('button').map(b=>b.textContent)).toEqual(['Build','Edit','Simulate','Projects']);
 expect(screen.getByText('Advanced Tools',{exact:true}).closest('details')).not.toHaveAttribute('open');
 fireEvent.click(screen.getByRole('button',{name:/Original GPT rover/}));fireEvent.change(screen.getByRole('slider',{name:'Unified measured timeline'}),{target:{value:'2'}});
 const time=screen.getByTestId('unified-measured-time').textContent;
 fireEvent.click(screen.getByRole('button',{name:'Edit'}));expect(screen.queryByRole('slider',{name:'Unified measured timeline'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Simulate'}));expect(screen.getByTestId('unified-measured-time')).toHaveTextContent(time!);
 fireEvent.click(screen.getByText('Advanced Tools',{exact:true}));expect(within(screen.getByRole('navigation',{name:'Project engineering sections'})).getAllByRole('button')).toHaveLength(8);
});
it('keeps selection and a head-bound draft across the contextual panel and width switches',async()=>{
 render(<UnifiedWorkspace/>);await screen.findByTestId('unified-project-identity');fireEvent.click(screen.getByRole('button',{name:'Inspect body floor'}));
 fireEvent.click(screen.getByRole('button',{name:'AI Assistant'}));fireEvent.change(screen.getByRole('textbox',{name:'Your engineering request'}),{target:{value:'Create my compact four-wheel rover'}});
 fireEvent.click(screen.getByRole('button',{name:'Expand AI panel'}));expect(screen.getByRole('separator',{name:'Resize right workspace panel'})).toHaveAttribute('aria-valuenow','420');
 fireEvent.click(screen.getByRole('button',{name:'Compact AI panel'}));fireEvent.click(screen.getByRole('button',{name:'Properties'}));expect(screen.getByTestId('unified-inspector')).toHaveAttribute('data-body-id','floor');
 fireEvent.click(screen.getByRole('button',{name:'AI Assistant'}));expect(screen.getByRole('textbox',{name:'Your engineering request'})).toHaveValue('Create my compact four-wheel rover');
 expect(call.mock.calls.every(x=>x.length===1)).toBe(true);
});
it('guides the original prompt into an exact empty head and consumes the handoff once',async()=>{
 const target={...current,snapshot:{...current.snapshot,key:'ai-review',project_sha256:'confirmed-target',project:structuredClone(rover.snapshot.project)}};
 call.mockImplementation(async(path:string)=>{if(path==='workspace?project=current')return structuredClone(current);if(path==='ai-engineering/new-project')return {project_key:'ai-review',project_sha256:'confirmed-target',revision:0};if(path==='workspace?project=ai-review')return structuredClone(target);throw new Error(path);});
 render(<UnifiedWorkspace/>);const prompt='Build me a four-wheel robot car.';await screen.findByRole('textbox');fireEvent.change(screen.getByRole('textbox'),{target:{value:prompt}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Set up robot workspace'}));
 await waitFor(()=>expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-sha256','confirmed-target'));expect(screen.getByRole('textbox')).toHaveValue(prompt);expect(screen.getByText(/Your workspace is ready. No robot has been created yet/)).toBeVisible();expect(screen.queryByLabelText('Verified proposal')).toBeNull();
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'A later draft for my four-wheel rover'}});fireEvent.click(screen.getByRole('button',{name:'Properties'}));fireEvent.click(screen.getByRole('button',{name:'AI Assistant'}));expect(screen.getByRole('textbox')).toHaveValue('A later draft for my four-wheel rover');expect(call.mock.calls.filter(([path])=>path==='ai-engineering/prepare')).toHaveLength(0);
});
it('rejects an actual head that differs from the setup response without carrying authority',async()=>{
 call.mockImplementation(async(path:string)=>{if(path==='workspace?project=current')return structuredClone(current);if(path==='ai-engineering/new-project')return {project_key:'ai-review',project_sha256:'promised',revision:0};if(path==='workspace?project=ai-review')return {...current,snapshot:{...current.snapshot,key:'ai-review',project_sha256:'different'}};throw new Error(path);});
 render(<UnifiedWorkspace/>);await screen.findByRole('textbox');fireEvent.change(screen.getByRole('textbox'),{target:{value:'Build me a four-wheel robot car.'}});stageLegacy();fireEvent.click(screen.getByRole('button',{name:'Set up robot workspace'}));await screen.findByRole('alert');expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-project',boot.project.id);expect(screen.getByRole('textbox')).toHaveValue('Build me a four-wheel robot car.');expect(call.mock.calls.filter(([path])=>path==='ai-engineering/prepare')).toHaveLength(0);
});

// Preserve the existing low-level protocol/recovery coverage under Advanced UI.
function stageLegacy(){const summary=screen.getAllByText('Usage & Safety').find(x=>x.parentElement?.classList.contains('studio-usage'))!;if(!summary.parentElement?.hasAttribute('open'))fireEvent.click(summary);fireEvent.click(screen.getByRole('button',{name:'Send request'}));}

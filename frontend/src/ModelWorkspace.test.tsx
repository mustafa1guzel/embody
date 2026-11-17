/** Explicit DOM protocol fixtures; no model authorship or physical outcome. */
import {render,screen,fireEvent,waitFor,within} from '@testing-library/react';
import {beforeEach,it,expect,vi} from 'vitest';
import ModelWorkspace,{roverPlaybackSample,type ModelDescriptor,type ModelProject} from './ModelWorkspace';
vi.mock('./WorldViewport',()=>({default:({selection,onSelect,world}:any)=><div data-testid="typed-design" data-world={world.id}>Selected {selection}<button onClick={()=>onSelect('chassis')}>Select actual chassis fixture</button></div>}));
vi.mock('./Editor',()=>({default:({file}:any)=><textarea aria-label="Controller fixture" readOnly value={file.content}/>}));
const descriptor:ModelDescriptor={id:'bounded_rover_ramp_v1',name:'Rover / inclined surface',fields:{chassis_mass_kg:{bounds:[.1,1.2],unit:'kg'},angle_deg:{bounds:[0,15],unit:'degrees'}},controller_id:'developer_rover_target_pd_v1',controller:{id:'developer_rover_target_pd_v1',content:'def controller_commands(): pass # DOM fixture, not live AI',sha256:'e'.repeat(64)},requirements:{minimumProgress:.005,maximumFinalSpeed:.1},source_sha256:'f'.repeat(64),verification:'CURRENT_SOURCE_NATIVE_QUALIFICATION_PENDING',execution:'IMPLEMENTED_REQUIRES_SEPARATE_EXACT_APPROVAL',limitations:['Rigid proxy only'],analytical:[],policy:{duration_s:1,timestep_s:.005,primary_steps_per_case:200,replay_steps_per_case:200},environment:'finite_planar_ramp_and_floor'};
const project:ModelProject={id:'a'.repeat(32),sha256:'b'.repeat(64),revision:0,declaration:{format:'EMBODY_ROBOT_PROJECT_V1',title:'Offline UI fixture',model_id:descriptor.id,controller_id:descriptor.controller_id,parameters:{chassis_mass_kg:.15,angle_deg:5},requirements:descriptor.requirements},verification:'NOT_VERIFIED',stale:false,kind:'NUMERIC_MODEL_PROJECT_NOT_APPLIED_WORLD'};
const design={world:{id:'fixture-world',objects:[{id:'chassis',name:'Chassis fixture',geometry:'box',mass_kg:.15,parent:'root',dimensions_m:[.18,.12,.012],joint:null,actuator:null,contact:{friction:[.7,.005,.0001]}}]},simulation:'NOT_RUN',total_dynamic_mass_kg:.292};
let requests:{path:string;body:any}[];let delayed:Promise<any>|null;
beforeEach(()=>{requests=[];delayed=null;vi.stubGlobal('fetch',vi.fn(async(path:string,options?:RequestInit)=>{const u=new URL(path,'http://localhost');const body=options?.body?JSON.parse(String(options.body)):undefined;requests.push({path:u.pathname,body});let value:any;
 if(u.pathname==='/api/toolkit/design')value=design;
 else if(u.pathname==='/api/toolkit/results')value={results:[]};
 else if(u.pathname==='/api/toolkit/prepare')value=delayed?await delayed:{request:{cases:[body.declaration.parameters]},primary_steps:200,fresh_replay_steps:200};
 else if(u.pathname==='/api/toolkit/save')value={...project,declaration:body.declaration,revision:1,sha256:'c'.repeat(64)};
 else throw Error('Unexpected path '+path);return {ok:true,json:async()=>value};}));});
function renderModel(view:'Design'|'Program'|'Simulate'|'Debug'|'Verify'='Design'){
 const onProject=vi.fn(),onExport=vi.fn(),onDirty=vi.fn(),onView=vi.fn();const props={project,descriptor,view,onProject,onExport,onDirty,onView,visible:true};return {...render(<ModelWorkspace {...props}/>),props,onProject,onExport,onDirty,onView};
}
it('opens actual design response without measurements and synchronizes component selection',async()=>{
 renderModel();await screen.findByTestId('typed-design');fireEvent.click(screen.getByRole('button',{name:'Select actual chassis fixture'}));expect(screen.getByText('Selected component')).toBeVisible();expect(screen.getByText(/0.292 kg/)).toBeVisible();expect(screen.getByText(/Compiled initial configuration only/)).toBeVisible();expect(requests.every(r=>!r.path.includes('start'))).toBe(true);
});
it('validates bounded parameters and never transfers a PASS to a draft',async()=>{
 const {onDirty}=renderModel();await screen.findByTestId('typed-design');fireEvent.change(screen.getByLabelText('Chassis mass model parameter'),{target:{value:'5'}});expect(screen.getByRole('alert')).toHaveTextContent('within');expect(screen.getByRole('button',{name:'Prepare model simulation'})).toBeDisabled();expect(screen.getByRole('button',{name:'Save robot configuration'})).toBeDisabled();expect(onDirty).toHaveBeenLastCalledWith(true);
});
it('prepares exact source-bound request and cancels before execution',async()=>{
 renderModel('Simulate');await screen.findByText('No current-source native results. There is no rover playback or physical PASS to show.');fireEvent.click(screen.getByRole('button',{name:'Prepare model simulation'}));const dialog=await screen.findByRole('dialog',{name:'Review model native request'});expect(within(dialog).getByRole('button',{name:/Run model simulation/})).toBeDisabled();expect(dialog).toHaveTextContent('200 primary + 200 fresh');fireEvent.click(within(dialog).getByRole('button',{name:'Cancel model execution preparation'}));expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(requests.some(r=>/start|execute|approve|apply/.test(r.path))).toBe(false);
});
it('shows registered readonly controller and rejects invented analytical support',async()=>{
 renderModel('Program');const code=await screen.findByLabelText('Controller fixture');expect(code).toHaveAttribute('readonly');expect(screen.getByText(/No steering or slip estimator/)).toBeVisible();expect(screen.getByText(/Native source compatibility and full application qualification are separate/)).toBeVisible();
});
it('keeps missing measurement debug state separate from physical failure',async()=>{
 renderModel('Debug');expect(await screen.findByText('UNVERIFIED — NO MEASUREMENTS')).toBeVisible();expect(screen.getByText(/No torque, slip or traction cause/)).toBeVisible();expect(screen.queryByText('REQUIREMENTS_PASS')).not.toBeInTheDocument();
});
it('tightened requirements preserve mandatory bounds and remain unmeasured',async()=>{
 renderModel('Verify');fireEvent.click(screen.getByText('Requirement thresholds'));fireEvent.change(screen.getByLabelText('Requirement minimumProgress'),{target:{value:'0'}});expect(screen.getByRole('alert')).toHaveTextContent('never weaken');expect(screen.getByText('NOT VERIFIED — no saved result selected')).toBeVisible();
});
it('uses explicit exact-head save and export only saved declaration',async()=>{
 const {onProject,onExport}=renderModel();await screen.findByTestId('typed-design');fireEvent.change(screen.getByLabelText('Chassis mass model parameter'),{target:{value:'.2'}});fireEvent.click(screen.getByRole('button',{name:'Save robot configuration'}));await waitFor(()=>expect(onProject).toHaveBeenCalled());const call=requests.find(r=>r.path==='/api/toolkit/save')!;expect(call.body.expected).toBe(project.sha256);expect(call.body.declaration.parameters.chassis_mass_kg).toBe(.2);fireEvent.click(screen.getByRole('button',{name:'Export saved robot project'}));expect(onExport).toHaveBeenCalledWith(project.declaration);
});
it('withholds a late prepared scope after parameter changes',async()=>{
 let resolve!:(v:any)=>void;delayed=new Promise(r=>{resolve=r;});renderModel();await screen.findByTestId('typed-design');fireEvent.click(screen.getByRole('button',{name:'Prepare model simulation'}));await waitFor(()=>expect(requests.some(r=>r.path.includes('prepare'))).toBe(true));fireEvent.change(screen.getByLabelText('Chassis mass model parameter'),{target:{value:'.25'}});resolve({request:{cases:[{}]},primary_steps:200,fresh_replay_steps:200});await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare model simulation'})).not.toBeDisabled());expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
it('rejects absent trajectory fields rather than manufacturing playback',()=>{
 expect(()=>roverPlaybackSample({time_s:0})).toThrow();expect(roverPlaybackSample({poses:[],contacts:[{}],qpos:[],qvel:[],actuator_force:[],time_s:.005}).contacts).toBe(1);
});
it('discards the model draft without applying or mutating the head',async()=>{
 renderModel();await screen.findByTestId('typed-design');fireEvent.change(screen.getByLabelText('Chassis mass model parameter'),{target:{value:'.2'}});fireEvent.click(screen.getByRole('button',{name:'Discard model draft'}));expect(screen.getByLabelText('Chassis mass model parameter')).toHaveValue(.15);expect(requests.every(r=>r.path!=='/api/toolkit/save')).toBe(true);
});

it('rejects coupled wheel overlap instead of silently resizing another field',async()=>{
 const p={...project,declaration:{...project.declaration,parameters:{...project.declaration.parameters,length_m:.18,wheel_radius_m:.06}}};
 render(<ModelWorkspace project={p} descriptor={descriptor} view="Design" onView={()=>{}} onProject={()=>{}} onDirty={()=>{}} onExport={()=>{}} visible/>);
 expect(screen.getByRole('alert')).toHaveTextContent('2 mm clearance');expect(screen.getByRole('button',{name:'Prepare model simulation'})).toBeDisabled();
});

it('never labels a loading rover as a rail configuration',()=>{
 renderModel('Verify');expect(screen.getByRole('button',{name:'Registered Rover / inclined surface configuration'})).toBeVisible();expect(screen.queryByRole('button',{name:'Registered rail configuration'})).not.toBeInTheDocument();
});

it('ignores a late saved-result response after a draft changes',async()=>{
 // Explicit protocol fixture; two synthetic presentation samples are not physics evidence.
 let finish!:(v:any)=>void;const pending=new Promise(resolve=>finish=resolve);const row={id:'native-fixture',case_id:'a'.repeat(64),sweep_id:'c'.repeat(32),verdict:'PASS',parameters:project.declaration.parameters,metrics:{},criteria:descriptor.requirements,source_sha256:descriptor.source_sha256};const original=globalThis.fetch;
 vi.stubGlobal('fetch',vi.fn(async(path:any,options?:RequestInit)=>{const u=new URL(String(path),'http://localhost');if(u.pathname==='/api/toolkit/results')return {ok:true,json:async()=>({results:[row],related_results:[row]})};if(u.pathname==='/api/toolkit/result')return {ok:true,json:async()=>await pending};return original(path,options);}));
 renderModel('Simulate');fireEvent.click(await screen.findByRole('button',{name:'Load saved PASS · '+row.case_id.slice(0,10)}));fireEvent.change(screen.getByLabelText('Chassis mass model parameter'),{target:{value:'.2'}});finish({record:{case_id:row.case_id,source_sha256:descriptor.source_sha256,samples:[]}});await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('Modified configuration — verification required'));expect(screen.queryByText('Play saved rover')).not.toBeInTheDocument();
});

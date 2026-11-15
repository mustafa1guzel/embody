/** Explicit protocol doubles; native evidence is verified by separate bounded backend tests. */
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import TrustedSweepPanel from './TrustedSweepPanel';
import raw from '../test/recorded-study.public.json?raw';
import {makePlan,parseAxis,defaultAxis,parseSweepStudy} from './parameterSweep';
const source='f'.repeat(64),id='b'.repeat(32),caseId='c'.repeat(64);
const catalog={experiment_id:'rail_velocity_brake_v1',controller_id:'developer_velocity_brake_v1',source_sha256:source,confirmation:'RUN TRUSTED RAIL SWEEP',policy:{wall_seconds:60},limitations:['UNIT TEST PROTOCOL DOUBLE'],recent:[{id,status:'COMPLETED'}]};
const fixture=JSON.parse(raw),data=parseSweepStudy(['A','B','C'].map(s=>fixture.experiments[s]));
const plan=()=>makePlan(data,'A','attempt_2',data.references[0].parameters,[parseAxis(defaultAxis('speed_mps'))],data.study.defaults);
const metrics={minimum_clearance_m:.1,final_speed_mps:0,maximum_speed_mps:1,wall_contact_episodes:0,wall_contact_samples:0,sampled_settling_time_s:1,sampled_settling_travel_m:.5,maximum_actuator_force_n:4};
const measured={case_id:caseId,parameters:data.references[0].parameters,execution_status:'MEASURED',verdict:'PASS',metrics,checks:{fixture_check:true},failure_reasons:[],comparison:{measured_minus_ideal_clearance_m:.01,sampled_travel_minus_ideal_stop_m:.01}};
const complete={sweep_id:id,status:'COMPLETED',cases:[measured],error:null,request:{cases:[measured.parameters],criteria:data.study.defaults,source_sha256:source,controller_id:catalog.controller_id},limitations:catalog.limitations};
const detail={...measured,source_sha256:source,controller_id:catalog.controller_id,effective_model_sha256:'e'.repeat(64),trajectory_sha256:'a'.repeat(64),engine_version:'TEST_DOUBLE',analytical_prediction:{stopping_distance_m:.49,stopping_time_s:1,remaining_clearance_m:.09},replay:{status:'PASS',primary_steps:600,fresh_steps:600},samples:[{time:0,position:0,velocity:1,wall_clearance:.6,wall_collision:false},{time:3,position:.5,velocity:0,wall_clearance:.1,wall_collision:false}]};
let calls:{path:string;body:any}[],current:any;
beforeEach(()=>{calls=[];current=structuredClone(complete);vi.stubGlobal('fetch',vi.fn(async(path:string,options?:RequestInit)=>{
 const body=options?.body?JSON.parse(String(options.body)):null;calls.push({path,body});let value;
 if(path==='/api/rail-sweeps/catalog')value=catalog;
 else if(path==='/api/rail-sweeps/start')value={sweep_id:id};
 else if(path.startsWith('/api/rail-sweeps/state?'))value=current;
 else if(path.startsWith('/api/rail-sweeps/case?'))value=detail;
 else if(path==='/api/rail-sweeps/cancel'){current={...current,status:'CANCELLED'};value=current;}
 else throw new Error('Unexpected '+path);
 return {ok:true,json:async()=>structuredClone(value)};
}));});
async function open(){render(<TrustedSweepPanel plan={plan()}/>);await screen.findByRole('button',{name:'Run Simulation Sweep'});}
async function load(){await open();fireEvent.change(screen.getByLabelText('Saved sweeps'),{target:{value:id}});fireEvent.click(screen.getByRole('button',{name:'Load saved sweep'}));await screen.findByLabelText('Native sweep progress');}
it('never executes on load or plan edits; rejects running without a valid preview',async()=>{
 const view=render(<TrustedSweepPanel plan={null}/>);await screen.findByLabelText('Trusted experiment');expect(screen.getByRole('button',{name:'Run Simulation Sweep'})).toBeDisabled();view.rerender(<TrustedSweepPanel plan={plan()}/>);expect(screen.getByRole('button',{name:'Run Simulation Sweep'})).toBeEnabled();expect(calls.every(c=>!c.body)).toBe(true);
});
it('requires explicit confirmation and dispatches only fixed developer identity/numeric parameters once',async()=>{
 await open();fireEvent.click(screen.getByRole('button',{name:'Run Simulation Sweep'}));expect(screen.getByRole('dialog')).toHaveTextContent('3 new reference experiments');expect(calls.filter(c=>c.body)).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Confirm and run trusted sweep'}));await screen.findByLabelText('Native sweep progress');const sent=calls.filter(c=>c.path==='/api/rail-sweeps/start');expect(sent).toHaveLength(1);expect(sent[0].body.controller_id).toBe('developer_velocity_brake_v1');expect(sent[0].body.cases).toEqual(plan().cases.map(c=>c.parameters));expect(sent[0].body).not.toHaveProperty('source');expect(sent[0].body).not.toHaveProperty('path');expect(sent[0].body.source_sha256).toBe(source);
});
it('dismisses an outdated confirmation when the numerical plan changes',async()=>{
 const view=render(<TrustedSweepPanel plan={plan()}/>);await screen.findByLabelText('Trusted experiment');fireEvent.click(screen.getByRole('button',{name:'Run Simulation Sweep'}));expect(screen.getByRole('dialog')).toBeInTheDocument();view.rerender(<TrustedSweepPanel plan={null}/>);expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(calls.filter(c=>c.body)).toHaveLength(0);
});
it('loads genuine-shaped saved results over GET only and uses reference titles without historical A/B/C relabelling',async()=>{
 await load();await screen.findByText(/MuJoCo TEST_DOUBLE/);expect(screen.getByLabelText('Native sweep progress')).toHaveTextContent('1 / 1 measured');expect(screen.getByLabelText('Recorded trajectory comparison')).toHaveTextContent('Trusted developer reference');expect(screen.getByLabelText('Recorded trajectory comparison')).not.toHaveTextContent('Solid: A');expect(calls.every(c=>!c.body)).toBe(true);
});
it('shows measured heatmap speed, verdict and signed discrepancy with separate units',async()=>{
 await load();fireEvent.change(screen.getByLabelText('Measured heatmap mode'),{target:{value:'speed'}});expect(screen.getByRole('button',{name:'Inspect measured case 1'})).toHaveTextContent('0 m/s');fireEvent.change(screen.getByLabelText('Measured heatmap mode'),{target:{value:'status'}});expect(screen.getByRole('button',{name:'Inspect measured case 1'})).toHaveTextContent('Measured PASS');fireEvent.change(screen.getByLabelText('Measured heatmap mode'),{target:{value:'discrepancy'}});expect(screen.getByRole('button',{name:'Inspect measured case 1'})).toHaveTextContent('0.01 m');
});
it('preserves measured failures, execution errors and partial completion without invented points',async()=>{
 current={...complete,status:'PARTIAL',error:'Case stopped',cases:[{...measured,verdict:'FAIL'},{case_id:'d'.repeat(64),parameters:{...measured.parameters,mass_kg:3},execution_status:'EXECUTION_ERROR',error:'Native error'},{case_id:'e'.repeat(64),parameters:{...measured.parameters,mass_kg:4},execution_status:'NOT_EXECUTED'}]};
 await load();expect(screen.getByLabelText('Native sweep progress')).toHaveTextContent('PARTIAL');expect(screen.getByRole('button',{name:'Inspect measured case 2'})).toHaveTextContent('EXECUTION ERROR');fireEvent.click(screen.getByRole('button',{name:'Inspect measured case 3'}));expect(screen.getByLabelText('Native case details')).toHaveTextContent('No verified trajectory');expect(screen.queryByLabelText('Recorded trajectory comparison')).not.toBeInTheDocument();
});
it('polls running progress without repeated start and explicitly cancels',async()=>{
 current={...complete,status:'RUNNING',cases:[{...measured,execution_status:'RUNNING',metrics:undefined}]};await load();expect(screen.getByRole('button',{name:'Run Simulation Sweep'})).toBeDisabled();expect(screen.getByRole('progressbar')).toHaveAttribute('value','0');
 fireEvent.click(screen.getByRole('button',{name:'Cancel sweep'}));await waitFor(()=>expect(screen.getByLabelText('Native sweep progress')).toHaveTextContent('CANCELLED'));expect(calls.filter(c=>c.path==='/api/rail-sweeps/cancel')).toHaveLength(1);expect(calls.filter(c=>c.path==='/api/rail-sweeps/start')).toHaveLength(0);
});
it('loads newly completed trajectory after a running selected case changes status',async()=>{
 current={...complete,status:'RUNNING',cases:[{...measured,execution_status:'RUNNING',metrics:undefined}]};await load();expect(screen.queryByLabelText('Recorded trajectory comparison')).not.toBeInTheDocument();current=structuredClone(complete);await screen.findByText(/MuJoCo TEST_DOUBLE/);expect(screen.getByLabelText('Recorded trajectory comparison')).toBeInTheDocument();
});
it('reports source/admission failure with no retries and exposes recoverable saved-run refresh',async()=>{
 await open();const previous=vi.mocked(fetch).getMockImplementation()!;vi.mocked(fetch).mockImplementation(async(...args)=>args[0]==='/api/rail-sweeps/start'?{ok:false,json:async()=>({error:'Source changed'})} as Response:previous(...args));
 fireEvent.click(screen.getByRole('button',{name:'Run Simulation Sweep'}));fireEvent.click(screen.getByRole('button',{name:'Confirm and run trusted sweep'}));expect(await screen.findByRole('alert')).toHaveTextContent('Run not retried');expect(screen.getByRole('button',{name:'Refresh saved sweeps'})).toBeEnabled();
});
it('exports only explicitly selected saved results and checks URLs are revoked',async()=>{
 await load();const create=vi.fn(()=> 'blob:fixture'),revoke=vi.fn();vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:revoke}));vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 fireEvent.click(screen.getByRole('button',{name:'Export measured sweep JSON'}));await waitFor(()=>expect(create).toHaveBeenCalledOnce());await waitFor(()=>expect(revoke).toHaveBeenCalled());expect(calls.filter(c=>c.body)).toHaveLength(0);
});
it('catalog/read failures leave analytical planning independent and never synthesize a measured result',async()=>{
 vi.mocked(fetch).mockResolvedValue({ok:false,json:async()=>({error:'Unavailable'})} as Response);render(<TrustedSweepPanel plan={plan()}/>);expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable');expect(screen.queryByLabelText('Native sweep progress')).not.toBeInTheDocument();
});

it('withholds the previous trajectory while a different measured case is still loading',async()=>{
 current={...complete,cases:[measured,{...measured,case_id:'d'.repeat(64),parameters:{...measured.parameters,mass_kg:3}}]};
 await load();await screen.findByText(/MuJoCo TEST_DOUBLE/);const previous=vi.mocked(fetch).getMockImplementation()!;
 let resolve:(v:Response)=>void=()=>{};
 vi.mocked(fetch).mockImplementation(async(...args)=>String(args[0]).includes('case='+ 'd'.repeat(64))?new Promise<Response>(r=>resolve=r):previous(...args));
 fireEvent.click(screen.getByRole('button',{name:'Inspect measured case 2'}));expect(screen.queryByLabelText('Recorded trajectory comparison')).not.toBeInTheDocument();
 await act(async()=>resolve({ok:true,json:async()=>({...detail,case_id:'d'.repeat(64)})} as Response));await screen.findByLabelText('Recorded trajectory comparison');
});

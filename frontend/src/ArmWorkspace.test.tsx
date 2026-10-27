import raw from '../test/arm_evidence.json?raw';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import ArmWorkspace,{ArmPlots} from './ArmWorkspace';
import type {Mode} from './types';
import {useState} from 'react';
const evidence=JSON.parse(raw);
// DOM interaction only: geometry/pose objects are tested separately with Three.
vi.mock('./Viewport',()=>({default:({sample}:any)=><div data-testid="arm-pose">{JSON.stringify(sample.geom_poses)}</div>}));
vi.mock('./Editor',()=>({default:({file,diff}:any)=><pre data-testid="arm-source">{diff?diff.original+'\n↔\n'+diff.modified:file.content}</pre>}));
let requests:{path:string;body:any}[]=[];let corrupt=false;
beforeEach(()=>{requests=[];corrupt=false;vi.stubGlobal('fetch',vi.fn(async(input:string,options?:RequestInit)=>{
 const url=new URL(input,'http://127.0.0.1');const path=url.pathname;requests.push({path,body:options?.body});let value;
 if(path==='/api/arm/recording')value=evidence.metadata;
 else if(path==='/api/arm/experiment'){
  if(corrupt)return {ok:false,json:async()=>({error:'Articulated pose mismatch'})};
  value=evidence.experiments[url.searchParams.get('scenario')!];
 }else if(path==='/api/arm/file')value=evidence.files[url.searchParams.get('path')!];
 else if(path==='/api/arm/proposal')value=evidence.proposal;
 else throw new Error('Unexpected request '+path);
 return {ok:true,json:async()=>value};
}));});
function Shell(){const [mode,setMode]=useState<Mode>('studio');return <ArmWorkspace mode={mode} onMode={setMode} onRail={vi.fn()}/>;}
it('opens actual recorded arm evidence with zero implicit actions and synchronized vectors',async()=>{
 render(<Shell/>);await screen.findByTestId('arm-time');
 expect(screen.getByText('1/801 measured states')).toBeInTheDocument();
 fireEvent.change(screen.getByRole('slider',{name:'Arm measured timeline'}),{target:{value:'400'}});
 const sample=evidence.experiments.arm_nominal.variants.original.samples[400];
 expect(screen.getByTestId('arm-time')).toHaveTextContent(sample.time.toFixed(3));
 expect(screen.getByTestId('arm-qpos_rad')).toHaveTextContent(sample.qpos_rad.map((v:number)=>v.toFixed(4)).join(' / '));
 expect(screen.getByTestId('arm-generalized_torque_nm')).toHaveTextContent(sample.generalized_torque_nm.map((v:number)=>v.toFixed(4)).join(' / '));
 expect(screen.getByTestId('arm-pose')).toHaveTextContent(JSON.stringify(sample.geom_poses));
 fireEvent.change(screen.getByRole('combobox',{name:'Arm playback controller'}),{target:{value:'attempt_1'}});
 expect(screen.getByText('1/801 measured states')).toBeInTheDocument();
 expect(requests.every(r=>!r.body)).toBe(true);
});
it('opens real files, exact model diff, recorded six-tool investigation and review gates',async()=>{
 render(<Shell/>);await screen.findByTestId('arm-time');
 fireEvent.click(screen.getByRole('button',{name:'robot/planar_arm.xml'}));
 await waitFor(()=>expect(screen.getByTestId('arm-source').textContent).toBe(evidence.files['robot/planar_arm.xml'].content));
 fireEvent.click(screen.getByRole('button',{name:'Open exact arm diff'}));
 await waitFor(()=>expect(screen.getByTestId('arm-source').textContent).toContain(evidence.proposal.source));
 expect(screen.getByTestId('arm-source').textContent).toContain(evidence.files['robot/arm_controller.py'].content);
 fireEvent.click(screen.getByRole('tab',{name:'Verification'}));
 expect(screen.getByRole('button',{name:'Review recorded candidate'})).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Verify in isolated VM'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Agent focus'}));
 expect(screen.getByText('15. propose_patch')).toBeInTheDocument();
 expect(document.querySelector('.arm-diagnosis')!.textContent).toBe(evidence.metadata.agent.diagnosis);
 expect(requests.every(r=>!r.body)).toBe(true);
});
it('reports task infeasibility with no invented arm motion',async()=>{
 render(<Shell/>);await screen.findByTestId('arm-time');
 fireEvent.change(screen.getByRole('combobox',{name:'Arm scenario'}),{target:{value:'arm_unreachable'}});
 await screen.findByText('No dynamic trajectory: task rejected by analytical feasibility.');
 expect(screen.queryByTestId('arm-pose')).not.toBeInTheDocument();
 expect(screen.queryByRole('slider',{name:'Arm measured timeline'})).not.toBeInTheDocument();
 expect(screen.getAllByText(/PROVEN_INFEASIBLE/).length).toBeGreaterThan(0);
});
it('fails visibly on invalid evidence and never substitutes a trajectory',async()=>{
 corrupt=true;render(<Shell/>);await screen.findByRole('alert');
 expect(screen.getByRole('alert')).toHaveTextContent('Articulated pose mismatch');
 expect(screen.queryByTestId('arm-pose')).not.toBeInTheDocument();
});
it('plots measured angles, velocities, torques and error at the exact selected sample',()=>{
 const samples=evidence.experiments.arm_nominal.variants.attempt_1.samples;
 render(<ArmPlots samples={samples} index={600} onSeek={vi.fn()}/>);
 expect(screen.getByTestId('arm-target_error_m')).toHaveTextContent(samples[600].target_error_m.toFixed(4));
 expect(document.querySelectorAll('.measured-path')).toHaveLength(4);
 expect(document.querySelectorAll('.comparison-path')).toHaveLength(3);
});

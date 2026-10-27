import evidenceRaw from '../test/recorded-study.public.json?raw';
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import * as THREE from 'three';
import {ActivityRail,ProjectDock,Inspector} from './ProjectDock';
import RecordedRun from './RecordedRun';
import {TimelineTracks} from './TimelineTracks';
import {Telemetry} from './Telemetry';
import {UnifiedDiff} from './UnifiedDiff';
import {fittedView,replayBounds} from './Viewport';
import {api,setToken} from './api';
const data=JSON.parse(evidenceRaw);
beforeEach(()=>{
 setToken('offline-fixture');
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>data.files['recording/agent_trace.jsonl']})));
});

describe('Day 7.2 navigation and truthful recorded agent',()=>{
 it('offers only implemented activity actions and opens actual grouped files',()=>{
  const view=vi.fn(),open=vi.fn();render(<><ActivityRail view="files" onView={view}/><ProjectDock view="files" files={data.bootstrap.files} active="robot/controller.py" dirty={['robot/controller.py']} selection="" onSelect={vi.fn()} onFile={open} onReset={vi.fn()} draftObject="" onDraftObject={vi.fn()}/></>);
  expect(within(screen.getByRole('navigation',{name:'Workbench tools'})).getAllByRole('button')).toHaveLength(3);
  fireEvent.click(screen.getByRole('button',{name:'Scene'}));expect(view).toHaveBeenCalledWith('scene');
  fireEvent.click(screen.getByRole('button',{name:'configs/bodybase.json'}));expect(open).toHaveBeenCalledWith('configs/bodybase.json');
  expect(screen.queryByRole('button',{name:'Assets'})).not.toBeInTheDocument();
  const group=screen.getByText('configs').closest('details')!;expect(group).toHaveAttribute('open');fireEvent.click(group.querySelector('summary')!);expect(group).not.toHaveAttribute('open');
 });
 it('shows measured inspector properties without a raw JSON default',()=>{
  const e=data.experiments.B,carriage=e.scene.bodies.find((o:any)=>o.name==='carriage');
  render(<Inspector object={carriage} scene={e.scene} sample={e.variants.original.samples[200]}/>);
  expect(screen.getByText('Mass (kg)').nextElementSibling).toHaveTextContent('3');
  expect(screen.getByText('Position (m)').nextElementSibling).toHaveTextContent(e.variants.original.samples[200].position.toFixed(1));
  expect(screen.getByText('Exact compiled properties').closest('details')).not.toHaveAttribute('open');
 });
 it('leads with the exact saved question and real proposal results, with all 17 calls collapsed',async()=>{
  const onProposal=vi.fn();render(<RecordedRun recorded={data.agent} onProposal={onProposal} onFile={vi.fn()}/>);
  const question=JSON.parse(data.files['recording/agent_trace.jsonl'].content.split('\n')[1]).payload.text;
  await waitFor(()=>expect(document.querySelector('.user-question p')?.textContent).toBe(question));
  expect(screen.getByText('Safety rejected')).toBeInTheDocument();expect(screen.getByText('Verified',{exact:true})).toBeInTheDocument();
  expect(screen.getByText('Run details · 17 tool calls').closest('details')).not.toHaveAttribute('open');
  expect(document.querySelectorAll('.tool-call')).toHaveLength(0);
  fireEvent.click(screen.getAllByRole('button',{name:'Review patch'})[0]);expect(onProposal).toHaveBeenCalledWith('attempt_1',false);
  fireEvent.click(screen.getAllByRole('button',{name:'Open diff'})[1]);expect(onProposal).toHaveBeenCalledWith('attempt_2',true);
  fireEvent.click(screen.getByText('Run details · 17 tool calls'));await waitFor(()=>expect(document.querySelectorAll('.tool-call')).toHaveLength(17));
 });
 it('copies exact tool data only on explicit action',async()=>{
  const copy=vi.fn().mockResolvedValue(undefined);vi.stubGlobal('navigator',Object.create(navigator,{clipboard:{value:{writeText:copy}}}));
  render(<RecordedRun recorded={data.agent}/>);fireEvent.click(screen.getByText('Run details · 17 tool calls'));await screen.findByText('01 read_project');fireEvent.click(screen.getByText('01 read_project'));
  fireEvent.click(screen.getAllByRole('button',{name:'Copy input'})[0]);await waitFor(()=>expect(copy).toHaveBeenCalledWith(JSON.stringify(data.agent.calls[0].arguments,null,2)));
  expect(fetch).toHaveBeenCalledTimes(1);expect(copy).toHaveBeenCalledTimes(1);
 });
 it('reports missing saved question, instead of inventing a prompt or model quotation',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({content:''})})));
  render(<RecordedRun recorded={data.agent}/>);await screen.findByText('Recorded task unavailable. Inspect the preserved trace.');
  expect(screen.queryByText('Why does the carriage hit the wall?')).not.toBeInTheDocument();
 });
});

describe('measured event tracks and telemetry',()=>{
 it('separates event symbols into three lanes and seeks exact stored sample indices',()=>{
  const t=data.experiments.A.variants.original,seek=vi.fn();render(<TimelineTracks trajectory={t} index={0} onSeek={seek}/>);
  expect(screen.getByText('Motion')).toBeInTheDocument();expect(screen.getByText('Contact')).toBeInTheDocument();expect(screen.getByText('Safety')).toBeInTheDocument();
  for(const marker of t.markers){const button=screen.getByRole('button',{name:'Seek '+marker.label});expect(button.textContent).not.toContain(marker.label);fireEvent.click(button);expect(seek).toHaveBeenLastCalledWith(marker.index);expect(button.title).toContain(marker.time.toFixed(3));}
  fireEvent.change(screen.getByRole('slider'),{target:{value:'417'}});expect(seek).toHaveBeenLastCalledWith(417);
 });
 it('does not fabricate contact or violation events for the verified trace',()=>{
  render(<TimelineTracks trajectory={data.experiments.A.variants.attempt_2} index={600} onSeek={vi.fn()}/>);
  expect(screen.queryByRole('button',{name:'Seek First contact'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Seek Clearance violation'})).not.toBeInTheDocument();
  expect(screen.getAllByText('None recorded')).toHaveLength(2);
 });
 it('uses actual context thresholds and keeps paths fixed while the measured cursor advances',()=>{
  const t=data.experiments.A.variants.original,seek=vi.fn();const props={trajectory:t,comparison:data.experiments.A.variants.attempt_2,index:0,onSeek:seek,minimumClearance:data.experiments.A.context.minimum_clearance_m};
  const view=render(<Telemetry {...props}/>),paths=[...document.querySelectorAll('.measured-path')].map(p=>p.getAttribute('d'));
  expect(screen.getByText('0.05 m minimum')).toBeInTheDocument();const before=screen.getAllByTestId('chart-cursor')[0].getAttribute('x1');
  view.rerender(<Telemetry {...props} index={400}/>);
  expect([...document.querySelectorAll('.measured-path')].map(p=>p.getAttribute('d'))).toEqual(paths);
  expect(screen.getAllByTestId('chart-cursor')[0].getAttribute('x1')).not.toBe(before);
  expect(screen.getByTestId('value-velocity')).toHaveTextContent(t.samples[400].velocity.toFixed(4));
  fireEvent.keyDown(screen.getByRole('img',{name:'Clearance over measured time'}),{key:'ArrowRight'});expect(seek).toHaveBeenLastCalledWith(401);
 });
 it('renders the exact unified diff with distinct additions and removals',()=>{
  const source=data.proposals.attempt_1.diff;const view=render(<UnifiedDiff source={source}/>);
  expect(screen.getByLabelText('Exact unified source diff').textContent).toBe(source);
  expect(view.container.querySelectorAll('.added').length).toBeGreaterThan(0);expect(view.container.querySelectorAll('.removed').length).toBeGreaterThan(0);
 });
});

describe('camera framing math, actual Three geometry, no GPU claim',()=>{
 it.each([1,1.5,2])('fits non-floor measured geometry within a perspective frustum at aspect %s',aspect=>{
  for(const e of Object.values(data.experiments) as any[]){
   const sample=e.variants.original.samples[0],bounds=replayBounds(e.scene,sample),view=fittedView(bounds,aspect);
   expect(bounds.getSize(new THREE.Vector3()).x).toBeLessThan(5); // excludes the 12 m display floor
   const camera=new THREE.PerspectiveCamera(42,aspect,.01,100);camera.up.set(0,0,1);camera.position.copy(view.position);camera.lookAt(view.target);camera.updateMatrixWorld(true);camera.updateProjectionMatrix();
   for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){const p=new THREE.Vector3(x,y,z).project(camera);expect(Math.abs(p.x)).toBeLessThan(1);expect(Math.abs(p.y)).toBeLessThan(1);}
   const selected=replayBounds(e.scene,sample,'geom:3');expect(selected.getSize(new THREE.Vector3()).x).toBeCloseTo(.26);
  }
 });
});

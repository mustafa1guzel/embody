import {expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import raw from '../test/engineering.json?raw';
import EngineeringWorkspace,{isCurrentDeviceRun} from './EngineeringWorkspace';
const {call,worldViews}=vi.hoisted(()=>({call:vi.fn(),worldViews:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args),job:vi.fn()}));
vi.mock('./WorldViewport',()=>({default:(props:any)=>{worldViews(props.world);return <button onClick={()=>props.onTransform('floor',[11,0,0],[0,0,0])}>Deterministic rejected-drag fixture</button>;}}));
it('refreshes authoritative geometry after a rejected optimistic drag; no inference or physics mocked as evidence',async()=>{
 const fixture=JSON.parse(raw);call.mockImplementation(async(path:string)=>{if(path==='engineering/bootstrap')return structuredClone(fixture);if(path==='engineering/edit')throw new Error('Invalid test transform');throw new Error('Unexpected fixture path '+path);});
 render(<EngineeringWorkspace/>);await screen.findByRole('button',{name:'Deterministic rejected-drag fixture'});const before=worldViews.mock.calls.at(-1)![0];
 fireEvent.click(screen.getByRole('button',{name:'Deterministic rejected-drag fixture'}));await screen.findByRole('alert');await waitFor(()=>expect(call.mock.calls.filter(c=>c[0]==='engineering/bootstrap')).toHaveLength(2));
 await waitFor(()=>expect(worldViews.mock.calls.at(-1)![0]).not.toBe(before));expect(worldViews.mock.calls.at(-1)![0]).toEqual(before);expect(screen.getByTestId('engineering-revision')).toHaveTextContent('Project r0');
});

it('never relabels recorded generated-world evidence after physical inputs change',()=>{
 const ids={world:'world_a',circuit:'circuit_a',device_contract:'contract_a'},run={generated_world_binding:true,contract:{world_sha256:'world_a',circuit_sha256:'circuit_a'}};
 expect(isCurrentDeviceRun(run,ids)).toBe(true);expect(isCurrentDeviceRun(run,{...ids,world:'world_b'})).toBe(false);expect(isCurrentDeviceRun(run,{...ids,circuit:'circuit_b'})).toBe(false);
});

import {beforeEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import raw from '../test/hardware.json?raw';
import HardwareWorkspace from './HardwareWorkspace';
const fixture=JSON.parse(raw);
vi.mock('./HardwareViewport',()=>({default:({assembly,selection,onSelect}:any)=><div data-testid="assembly-view"><span>{selection}</span><button onClick={()=>onSelect('sensor')}>Select sensor mesh</button><pre>{JSON.stringify(assembly)}</pre></div>}));
vi.mock('./DeviceViewport',()=>({default:({sample}:any)=><div data-testid="device-pose">{JSON.stringify(sample.geom_poses)}</div>}));
vi.mock('./Editor',()=>({default:({file}:any)=><pre data-testid="device-source">{file.content}</pre>}));
let requests:{path:string;body:any}[]=[];
beforeEach(()=>{requests=[];localStorage.clear();vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
 const path=new URL(url,'http://127.0.0.1').pathname,body=options?.body?JSON.parse(String(options.body)):undefined;requests.push({path,body});let value;
 if(path==='/api/hardware/bootstrap')value=fixture.bootstrap;
 else if(path==='/api/hardware/validate')value=body.assembly.wires.length>fixture.bootstrap.template.wires.length?fixture.invalid_diagnostics:fixture.diagnostics;
 else if(path==='/api/hardware/edit')value=body.operation.kind==='connect'?fixture.invalid:fixture.moved;
 else if(path==='/api/hardware/save')value={key:'a'.repeat(64),assembly:body.assembly};
 else if(path==='/api/hardware/load')value=fixture.moved;
 else if(path==='/api/device/run')value={job_id:'reference_fixture'};
 else if(path==='/api/job')value={status:'COMPLETED',result:fixture.run};
 else if(path==='/api/hardware/propose')value={status:'PROPOSED_NOT_APPLIED',origin:'manual_data_proposal',operations:body.operations,diagnostics:fixture.diagnostics};
 else throw new Error('Unexpected request '+path);
 return {ok:true,json:async()=>structuredClone(value)};
}));});
it('opens a real catalog and graph with synchronized selection and no implicit simulation',async()=>{
 render(<HardwareWorkspace visible/>);await screen.findByTestId('assembly-view');
 expect(screen.getByText('Sensor-controlled barrier · human-defined template')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Select sensor mesh'}));
 expect(screen.getByRole('textbox',{name:'Instance name'})).toHaveValue('sensor');
 expect(screen.getByTestId('assembly-view')).toHaveTextContent('sensor');
 expect(requests.every(r=>!['/api/device/run','/api/agent/live','/api/review/action'].includes(r.path))).toBe(true);
});
it('sends actual finite transforms to backend, persists and reloads graph identities',async()=>{
 render(<HardwareWorkspace visible/>);await screen.findByTestId('assembly-view');
 fireEvent.change(screen.getByRole('spinbutton',{name:'Position (m) X'}),{target:{value:'.1'}});
 fireEvent.click(screen.getByRole('button',{name:'Apply transform'}));
 await waitFor(()=>expect(requests.find(r=>r.path==='/api/hardware/edit')?.body.operation.position_m[0]).toBe(.1));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Save assembly'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Save assembly'}));await screen.findByText(/Saved immutable assembly/);
 fireEvent.click(screen.getByRole('button',{name:'Reload saved assembly'}));await screen.findByText(/Reloaded equivalent graph/);
 expect(screen.getByTestId('assembly-view')).toHaveTextContent('0.1');
});
it('uses real pin endpoints for graph wiring and inspectable reference source',async()=>{
 render(<HardwareWorkspace visible/>);await screen.findByTestId('assembly-view');
 fireEvent.change(screen.getByRole('combobox',{name:'Source pin'}),{target:{value:'sensor.ECHO'}});
 fireEvent.change(screen.getByRole('combobox',{name:'Target pin'}),{target:{value:'board.IO19'}});
 fireEvent.click(screen.getByRole('button',{name:'Connect pins'}));
 await waitFor(()=>expect(requests.find(r=>r.path==='/api/hardware/edit')?.body.operation.a).toEqual({component:'sensor',pin:'ECHO'}));
 fireEvent.click(screen.getByRole('button',{name:'Code'}));
 expect(await screen.findByTestId('device-source')).toHaveTextContent('class ReferenceLogic');
});
it('runs only on explicit action and replays exact measured native geometry',async()=>{
 render(<HardwareWorkspace visible/>);await screen.findByTestId('assembly-view');
 fireEvent.click(screen.getByRole('button',{name:'Studio'}));
 expect(screen.queryByTestId('device-pose')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Run trusted MuJoCo experiment'}));
 await screen.findByTestId('device-pose');
 fireEvent.change(screen.getByRole('slider',{name:'Device measured time'}),{target:{value:'1'}});
 expect(screen.getByTestId('device-pose')).toHaveTextContent(JSON.stringify(fixture.run.samples[1].geom_poses));
 expect(requests.filter(r=>r.path==='/api/device/run')).toHaveLength(1);
 expect(requests.find(r=>r.path==='/api/device/run')?.body.assembly.id).toBe('sensor_barrier');
});
it('proposes a wiring change without automatic apply or simulator execution',async()=>{
 render(<HardwareWorkspace visible/>);await screen.findByTestId('assembly-view');
 fireEvent.click(screen.getByRole('button',{name:'Agent / review'}));fireEvent.click(screen.getByRole('button',{name:'Propose selected connection'}));
 await screen.findByText(/PROPOSED · NOT APPLIED/);
 expect(screen.getByRole('button',{name:'Apply reviewed wiring change'})).toBeInTheDocument();
 expect(requests.some(r=>r.path==='/api/hardware/apply'||r.path==='/api/device/run')).toBe(false);
});
it('runs the supported physical variation through the existing trusted device endpoint',async()=>{
 render(<HardwareWorkspace visible/>);await screen.findByTestId('assembly-view');
 fireEvent.click(screen.getByRole('button',{name:'Studio'}));
 fireEvent.change(screen.getByRole('combobox',{name:'Device experiment'}),{target:{value:'variation_mass'}});
 fireEvent.click(screen.getByRole('button',{name:'Run trusted MuJoCo experiment'}));
 await screen.findByTestId('device-pose');
 const request=requests.find(r=>r.path==='/api/device/run')!;
 expect(request.body.spec.mechanical.mass_kg).toBe(.04);
 expect(request.body.spec.requirements).toEqual(fixture.bootstrap.device_spec.requirements);
 expect(request.body.assembly).toEqual(fixture.bootstrap.template);
 expect(requests.some(r=>r.path.startsWith('/api/agent/'))).toBe(false);
});

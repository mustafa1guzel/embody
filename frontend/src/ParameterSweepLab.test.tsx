import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {beforeEach, expect, it, vi} from 'vitest';
import raw from '../test/recorded-study.public.json?raw';
import unifiedRaw from '../test/unified.json?raw';
import engineeringRaw from '../test/engineering.json?raw';
import ParameterSweepLab from './ParameterSweepLab';
import App from './App';
const evidence = JSON.parse(raw), rover = JSON.parse(unifiedRaw), engineering = JSON.parse(engineeringRaw);
vi.mock('./Editor', () => ({default: () => <div>Existing editor DOM fixture</div>}));
vi.mock('./Viewport', () => ({default: () => <div>Existing rail DOM fixture</div>}));
vi.mock('./WorldViewport', () => ({default: () => <div>Existing world DOM fixture</div>}));
let requests: {path: string; options: unknown}[];
beforeEach(() => {
 requests=[];localStorage.clear();vi.stubGlobal('fetch',vi.fn(async(path:string,options?:unknown)=>{
  requests.push({path,options});const u=new URL(path,'http://127.0.0.1');let data;
  if(u.pathname==='/api/rail-sweeps/catalog')data={experiment_id:'rail_velocity_brake_v1',controller_id:'developer_velocity_brake_v1',source_sha256:'f'.repeat(64),confirmation:'RUN TRUSTED RAIL SWEEP',policy:{},limitations:[],recent:[]};
  else if(u.pathname==='/api/experiment')data=evidence.experiments[u.searchParams.get('scenario')!];
  else if(u.pathname==='/api/bootstrap')data=evidence.bootstrap;
  else if(u.pathname==='/api/agent/recorded')data=evidence.agent;
  else if(u.pathname==='/api/proposal')data=evidence.proposals[u.searchParams.get('variant')!];
  else if(u.pathname==='/api/file')data=evidence.files[u.searchParams.get('path')!];
  else if(u.pathname==='/api/workspace')data={...rover,snapshot:{...rover.snapshot,key:'current',project:engineering.project,project_sha256:engineering.identities.project,historical:false,editable:true,runs:[],proposals:[],shape_parts:[]}};
  else throw new Error('Unexpected route '+path);
  return {ok:true,json:async()=>structuredClone(data)};
 }));
});
async function open(){render(<ParameterSweepLab/>);await screen.findByRole('button',{name:'Preview analytical plan'});}
function preview(){fireEvent.click(screen.getByRole('button',{name:'Preview analytical plan'}));}
it('loads actual reference data; edits and analytical preview make no execution requests',async()=>{
 await open();expect(screen.getByText(/proposed experiments/)).toHaveTextContent('9');expect(screen.queryByRole('table')).not.toBeInTheDocument();preview();expect(screen.getByRole('table')).toHaveTextContent('Initial velocity toward wall');expect(screen.getAllByTestId(/^sweep-cell-/)).toHaveLength(9);
 expect(screen.getByLabelText('Sweep summary')).toHaveTextContent('0 / 9');expect(screen.getByRole('button',{name:'Run Simulation Sweep'})).toBeEnabled();expect(requests).toHaveLength(4);expect(requests.every(r=>r.options===undefined)).toBe(true);
});
it('selects heatmap cells and exposes independent analytical values with no measured substitution',async()=>{
 await open();preview();fireEvent.click(screen.getByTestId('sweep-cell-5'));const detail=screen.getByRole('complementary',{name:'Selected experiment details'});
 expect(detail).toHaveTextContent('Ideal stopping distance0.36 m');expect(detail).toHaveTextContent('NOT EXECUTED');expect(detail).toHaveTextContent('Original verdict: PASS');expect(detail).toHaveTextContent('0.0524 m');expect(screen.getByLabelText('Recorded trajectory comparison')).toBeInTheDocument();
 fireEvent.click(screen.getByTestId('sweep-cell-0'));expect(detail).toHaveTextContent('no exact-anchor saved recording');expect(screen.queryByLabelText('Recorded trajectory comparison')).not.toBeInTheDocument();
});
it('keeps prediction and historical measured heatmap modes distinct, with missing values unavailable',async()=>{
 await open();preview();fireEvent.change(screen.getByLabelText('Heatmap mode'),{target:{value:'clearance'}});
 expect(screen.getByTestId('sweep-cell-0')).toHaveTextContent('Unavailable');expect(screen.getByTestId('sweep-cell-5')).toHaveTextContent('0.0524 m');expect(screen.getByTestId('sweep-cell-5')).toHaveTextContent('recorded PASS');
 fireEvent.change(screen.getByLabelText('Heatmap mode'),{target:{value:'status'}});expect(screen.getByTestId('sweep-cell-0')).toHaveTextContent('Insufficient data');expect(screen.getByTestId('sweep-cell-5')).toHaveTextContent('Derived PASS');expect(screen.getByTestId('sweep-cell-5')).toHaveTextContent('Not executed');
});
it('shows the real original failure against an ideal within-limits prediction',async()=>{
 await open();fireEvent.change(screen.getByLabelText('Recorded controller identity'),{target:{value:'original'}});preview();fireEvent.click(screen.getByTestId('sweep-cell-5'));
 expect(screen.getByLabelText('Historical anchor comparison')).toHaveTextContent('Original verdict: FAIL');expect(screen.getByLabelText('Failure boundary analysis')).toHaveTextContent('1 disagree');expect(screen.getByLabelText('Historical anchor comparison')).toHaveTextContent('Unavailable');
});
it('clears stale previews on edit, rejects invalid steps/counts and recovers with reset',async()=>{
 await open();preview();fireEvent.change(screen.getByLabelText('Horizontal step'),{target:{value:'0'}});expect(screen.queryByRole('table')).not.toBeInTheDocument();expect(screen.getByRole('alert')).toHaveTextContent('positive step');expect(screen.getByRole('button',{name:'Preview analytical plan'})).toBeDisabled();expect(screen.queryByRole('button',{name:'Export plan JSON'})).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Horizontal step'),{target:{value:'.01'}});expect(screen.getByRole('alert')).toHaveTextContent('25');fireEvent.click(screen.getByRole('button',{name:'Reset to defaults'}));expect(screen.queryByRole('alert')).not.toBeInTheDocument();preview();expect(screen.getAllByTestId(/^sweep-cell-/)).toHaveLength(9);
});
it('rejects duplicate axes, unsupported force, blank criteria and exclusive zero speed',async()=>{
 await open();fireEvent.change(screen.getByLabelText('Vertical parameter'),{target:{value:'speed_mps'}});expect(screen.getByRole('alert')).toHaveTextContent('distinct');
 fireEvent.click(screen.getByRole('button',{name:'Reset to defaults'}));fireEvent.change(screen.getByLabelText('Fixed Maximum braking force'),{target:{value:'0'}});expect(screen.getByRole('alert')).toHaveTextContent('2–6');
 fireEvent.click(screen.getByRole('button',{name:'Reset to defaults'}));fireEvent.change(screen.getByLabelText('Maximum final speed (exclusive)'),{target:{value:'0'}});expect(screen.getByRole('alert')).toHaveTextContent('positive');
 fireEvent.change(screen.getByLabelText('Maximum final speed (exclusive)'),{target:{value:''}});expect(screen.getByRole('button',{name:'Preview analytical plan'})).toBeDisabled();
});
it('supports a one-axis plan and actual selected reference parameters without claiming execution',async()=>{
 await open();fireEvent.click(screen.getByLabelText('Vary a second parameter'));fireEvent.change(screen.getByLabelText('Reference experiment'),{target:{value:'C'}});expect(screen.getByLabelText('Fixed Initial surface clearance')).toHaveValue(1.42);preview();expect(screen.getAllByTestId(/^sweep-cell-/)).toHaveLength(3);expect(screen.getByLabelText('Sweep summary')).toHaveTextContent('0 / 3');
});
it('updates selected criteria while preserving historical verdict and actual saved measurement',async()=>{
 await open();fireEvent.change(screen.getByLabelText('Recorded controller identity'),{target:{value:'attempt_1'}});fireEvent.change(screen.getByLabelText('Required minimum clearance'),{target:{value:'.02'}});preview();fireEvent.click(screen.getByTestId('sweep-cell-5'));
 const comparison=screen.getByLabelText('Historical anchor comparison');expect(comparison).toHaveTextContent('Original verdict: FAIL');expect(comparison).toHaveTextContent('Derived selected criteria: PASS');expect(comparison).toHaveTextContent('0.0249 m');
});
it('exports explicit JSON only on user action and revokes the object URL',async()=>{
 await open();preview();const create=vi.fn(()=> 'blob:local-plan'),revoke=vi.fn();vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:revoke}));const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 fireEvent.click(screen.getByRole('button',{name:'Export plan JSON'}));expect(create).toHaveBeenCalledOnce();expect(create.mock.calls[0]).toHaveLength(1);expect(click).toHaveBeenCalledOnce();await new Promise(resolve=>setTimeout(resolve,10));expect(revoke).toHaveBeenCalledWith('blob:local-plan');expect(requests).toHaveLength(4);
});
it('shows loading/read errors without fallback results and allows an explicit GET retry',async()=>{
 vi.mocked(fetch).mockResolvedValue({ok:false,json:async()=>({error:'Evidence hash mismatch'})} as Response);render(<ParameterSweepLab/>);expect(screen.getByRole('status')).toHaveTextContent('Loading');expect(await screen.findByRole('alert')).toHaveTextContent('Evidence hash mismatch');expect(screen.queryByRole('table')).not.toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Retry saved reference read'}));await screen.findByRole('alert');expect(requests.every(r=>r.options===undefined)).toBe(true);
});
it('ignores an interrupted asynchronous read after unmount',async()=>{
 let finish:(v:Response)=>void=()=>{};vi.mocked(fetch).mockImplementationOnce(()=>new Promise<Response>(resolve=>finish=resolve));const v=render(<ParameterSweepLab/>);v.unmount();await act(async()=>finish({ok:true,json:async()=>evidence.experiments.A} as Response));expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
it('is mounted in real App Simulate navigation, connects to Regression Explorer and preserves the head',async()=>{
 render(<App/>);await screen.findByTestId('unified-project-identity');const identity=screen.getByTestId('unified-project-identity').getAttribute('data-project');fireEvent.click(screen.getByRole('button',{name:'Simulate'}));fireEvent.click(screen.getByRole('button',{name:'Open Parameter Sweep Lab'}));await screen.findByRole('button',{name:'Preview analytical plan'});expect(screen.getByLabelText('Parameter Sweep Lab').closest('.ide')).toHaveClass('sweep-mode');preview();
 fireEvent.click(screen.getByRole('button',{name:'Compare recorded controllers'}));await screen.findByLabelText('Derived engineering summary');fireEvent.click(screen.getByRole('button',{name:'Plan a parameter sweep'}));await screen.findByRole('button',{name:'Preview analytical plan'});fireEvent.click(screen.getByRole('button',{name:'Back to workbench'}));expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-project',identity);expect(requests.every(r=>r.options===undefined)).toBe(true);
},12000);

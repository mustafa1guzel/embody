// Explicit UI protocol fixtures. Native physics is tested independently in Python/Chrome.
import {render,screen,waitFor,fireEvent,act} from '@testing-library/react';
import {beforeEach,describe,it,expect,vi} from 'vitest';
import LocalWorkbench,{verificationReport} from './LocalWorkbench';
import {api} from './api';
vi.mock('./api',()=>({api:vi.fn(),setToken:vi.fn()}));
vi.mock('./ControllerWorkbench',()=>({default:()=> <div>UNIT source tools fixture, not execution</div>}));
vi.mock('./Viewport',()=>({default:()=> <div>UNIT viewport fixture, not physics</div>}));
const d={format:'EMBODY_ROBOT_CONFIGURATION_V1',title:'Fixture project',model_id:'rail_carriage',controller_id:'developer_velocity_brake_v1',parameters:{mass_kg:4,speed_mps:1.2,force_n:2,gap_m:1.44},requirements:{minimumClearance:.05,maximumFinalSpeed:.03,maximumSettlingTime:3,maximumContactEpisodes:0}};
const base={id:'a'.repeat(32),sha256:'b'.repeat(64),revision:0,source:JSON.stringify(d,null,2)+'\n',declaration:d,design:{},controller:'UNIT fixture controller',runs:[],reviews:[]};
const catalog={csrf_token:'UNIT_TOKEN',projects:[{id:base.id,title:base.declaration.title,revision:0}],units:{force_n:'N'},save_confirmation:'SAVE REVIEWED ROBOT CONFIGURATION',run_confirmation:'RUN ONE LOCAL TRUSTED RAIL VERIFICATION'};
let current:any,review:any;
beforeEach(()=>{current=structuredClone(base);review={review_id:'c'.repeat(64),origin:'HUMAN_AUTHORED_JSON',verification:'COMPILED_NOT_PHYSICALLY_VERIFIED',diff:'- force_n:2\n+ force_n:4',before:d,after:{...d,parameters:{...d.parameters,force_n:4}},design:{}};vi.mocked(api).mockReset();vi.mocked(api).mockImplementation(async(path,b:any)=>{
 if(path==='workbench/bootstrap')return catalog;
 if(path==='workbench/create'||path.startsWith('workbench/project?'))return current;
 if(path==='workbench/review'){if(b.source==='bad')throw Error('Invalid bounded JSON');return review;}
 if(path==='workbench/decide'){if(b.decision==='SAVE')current={...current,sha256:'d'.repeat(64),revision:1,declaration:review.after,source:JSON.stringify(review.after,null,2)+'\n'};return current;}
 throw Error('Unexpected UNIT request '+path);
});});
async function opened(){render(<LocalWorkbench/>);await waitFor(()=>expect(screen.getByRole('button',{name:'New rail project'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'New rail project'}));await screen.findByRole('heading',{name:'Saved system context'});}
function source(){fireEvent.click(screen.getByRole('button',{name:'Source'}));return screen.getByLabelText('Project JSON source');}
describe('local workbench review and truth boundaries',()=>{
 it('starts without paid/native actions and labels the offline scope',async()=>{render(<LocalWorkbench/>);await screen.findByRole('button',{name:'New rail project'});expect(screen.getByText(/offline tools/)).toBeInTheDocument();expect(vi.mocked(api).mock.calls.every(([path])=>path==='workbench/bootstrap')).toBe(true);});
 it('keeps source edits as drafts until review and a separate explicit save',async()=>{await opened();fireEvent.change(source(),{target:{value:JSON.stringify(review.after)}});fireEvent.click(screen.getByRole('button',{name:'Review JSON changes'}));await screen.findByRole('heading',{name:'Review configuration change'});expect(screen.getByRole('button',{name:'Save reviewed configuration'})).toBeDisabled();expect(api).not.toHaveBeenCalledWith('workbench/decide',expect.anything());fireEvent.click(screen.getByLabelText('I reviewed this configuration change'));fireEvent.click(screen.getByRole('button',{name:'Save reviewed configuration'}));await waitFor(()=>expect(screen.getByText('Saved r1')).toBeInTheDocument());expect(api).toHaveBeenCalledWith('workbench/decide',expect.objectContaining({expected:base.sha256,decision:'SAVE',confirmation:catalog.save_confirmation}));});
 it('surfaces a real rejection shape and does not persist invalid source',async()=>{await opened();fireEvent.change(source(),{target:{value:'bad'}});fireEvent.click(screen.getByRole('button',{name:'Review JSON changes'}));expect(await screen.findByRole('alert')).toHaveTextContent('Invalid bounded JSON');expect(api).not.toHaveBeenCalledWith('workbench/decide',expect.anything());});
 it('discards a source draft and review without simulation',async()=>{await opened();const editor=source();fireEvent.change(editor,{target:{value:JSON.stringify(review.after)}});fireEvent.click(screen.getByRole('button',{name:'Review JSON changes'}));await screen.findByRole('heading',{name:'Review configuration change'});fireEvent.click(screen.getByLabelText('I reviewed this configuration change'));fireEvent.click(screen.getByRole('button',{name:'Discard review'}));await waitFor(()=>expect(screen.queryByRole('heading',{name:'Review configuration change'})).not.toBeInTheDocument());expect(screen.getByLabelText('Project JSON source')).toHaveValue(base.source);expect(api).not.toHaveBeenCalledWith('workbench/start',expect.anything());});
 it('requires explicit run consent and refuses to run a source draft',async()=>{await opened();const run=screen.getByRole('button',{name:'Run native verification'});expect(run).toBeDisabled();fireEvent.click(screen.getByLabelText(/Run one trusted rail case/));expect(run).toBeEnabled();fireEvent.change(source(),{target:{value:JSON.stringify(review.after)}});expect(run).toBeDisabled();});
 it('shows separate physical and replay outcomes and invalidates old head after save',async()=>{await opened();const record={verdict:'FAIL',checks:{selected_clearance:false,fresh_replay:true},metrics:{minimum_clearance_m:.003},parameters:d.parameters,criteria:d.requirements,replay_status:'PASS',independent_verification:'UNIT_READBACK',source_sha256:'fixture'};let done=false;
 vi.mocked(api).mockImplementation(async(path,b:any)=>{if(path==='workbench/bootstrap')return catalog;if(path==='workbench/start')return {sweep_id:'e'.repeat(32)};if(path.startsWith('workbench/run?'))return {verified:true,state:{status:'COMPLETED'},record,association:{project_revision:0,project_sha256:base.sha256},same_head:true,samples:[],scene:{}};if(path.startsWith('workbench/project?'))return current;if(path==='workbench/suggest')return review;if(path==='workbench/decide'){done=true;current={...current,revision:1,sha256:'d'.repeat(64),source:JSON.stringify(review.after),declaration:review.after};return current;}throw Error(path);});
 fireEvent.click(screen.getByLabelText(/Run one trusted rail case/));fireEvent.click(screen.getByRole('button',{name:'Run native verification'}));await screen.findByText('FAIL · measured physical requirements');expect(screen.getByText(/Fresh replay: PASS/)).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Propose bounded authority change'}));await screen.findByRole('heading',{name:'Review configuration change'});fireEvent.click(screen.getByLabelText('I reviewed this configuration change'));fireEvent.click(screen.getByRole('button',{name:'Save reviewed configuration'}));await waitFor(()=>expect(done).toBe(true));expect(screen.getByText(/Earlier head: this result does not verify/)).toBeInTheDocument();expect(screen.getByRole('button',{name:'Propose bounded authority change'})).toBeDisabled();});
 it('drops a late source review when another project was opened',async()=>{await opened();let resolve:(v:any)=>void=()=>{};const pending=new Promise(r=>resolve=r);const old=vi.mocked(api).getMockImplementation()!;vi.mocked(api).mockImplementation((p,b)=>p==='workbench/review'?pending:old(p,b));fireEvent.change(source(),{target:{value:JSON.stringify(review.after)}});fireEvent.click(screen.getByRole('button',{name:'Review JSON changes'}));fireEvent.click(screen.getByRole('button',{name:/Fixture project Revision 0/}));await screen.findByText('Saved configuration opened. Physical evidence remains separate.');await act(async()=>resolve(review));expect(screen.queryByRole('heading',{name:'Review configuration change'})).not.toBeInTheDocument();});
});

// Regression: numerical spelling in the exported server document is hash-bound.
describe('verification document export',()=>{
 it('preserves exact JSON bytes instead of normalizing 4.0 to 4',async()=>{
  const raw='{"parameters":{"mass_kg":4.0},"report_sha256":"SERVER_HASH"}';
  const transport=vi.fn().mockResolvedValue(new Response(raw,{headers:{'content-type':'application/json'}}));
  vi.stubGlobal('fetch',transport);
  try{const exported=await verificationReport('a'.repeat(32),'b'.repeat(32));expect(await exported.text()).toBe(raw);expect(transport).toHaveBeenCalledWith('/api/workbench/report?id='+'a'.repeat(32)+'&nonce='+'b'.repeat(32),{credentials:'same-origin'});}
  finally{vi.unstubAllGlobals();}
 });
 it('exports nothing when verified evidence cannot be read',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:400})));
  try{await expect(verificationReport('a'.repeat(32),'b'.repeat(32))).rejects.toThrow('no replacement was exported');}
  finally{vi.unstubAllGlobals();}
 });
});

describe('asynchronous workspace isolation',()=>{
 it('ignores a JSON file that finishes reading after a project reopen',async()=>{
  await opened();source();let resolve:(v:string)=>void=()=>{};const pending=new Promise<string>(r=>resolve=r);
  fireEvent.change(screen.getByLabelText('Load project JSON draft'),{target:{files:[{size:20,text:()=>pending}]}});
  fireEvent.click(screen.getByRole('button',{name:/Fixture project Revision 0/}));
  await screen.findByText('Saved configuration opened. Physical evidence remains separate.');
  await act(async()=>resolve('OLD_CONTEXT_DRAFT'));
  expect(screen.getByLabelText('Project JSON source')).toHaveValue(base.source);
 });
 it('does not attach a late request error to a reopened project',async()=>{
  await opened();let reject:(e:Error)=>void=()=>{};const pending=new Promise((_,r)=>reject=r);const old=vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation((p,b)=>p==='workbench/review'?pending:old(p,b));
  fireEvent.change(source(),{target:{value:JSON.stringify(review.after)}});fireEvent.click(screen.getByRole('button',{name:'Review JSON changes'}));
  fireEvent.click(screen.getByRole('button',{name:/Fixture project Revision 0/}));await screen.findByText('Saved configuration opened. Physical evidence remains separate.');
  await act(async()=>reject(new Error('STALE_REVIEW_FAILURE')));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
 });
});

it('shows source verification count rather than the unused numerical-reference count',async()=>{
 current={...current,controller_source:{head_sha256:'f'.repeat(64),runs:[{nonce:'1'},{nonce:'2'}]}};
 await opened();expect(screen.getByRole('button',{name:'Verification runs (2)'})).toBeInTheDocument();expect(screen.queryByRole('button',{name:'Verification runs (0)'})).not.toBeInTheDocument();
});

import evidenceRaw from '../test/recorded-study.public.json?raw';
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import App from './App';
import PatchReview from './PatchReview';
import {setToken} from './api';
const evidence=JSON.parse(evidenceRaw);
// DOM-only shell tests replace the heavy render surfaces. Separate tests below
// exercise actual Monaco models, Three geometry and measured pose application.
vi.mock('./Editor',()=>({default:({file,draft,onChange,diff}:any)=><div>{diff?<pre data-testid="diff-source">{diff.original+'\n↔\n'+diff.modified}</pre>:<textarea aria-label="Monaco draft surface (DOM test)" readOnly={file.historical} value={draft} onChange={e=>onChange(e.target.value)}/>}</div>}));
vi.mock('./UnifiedWorkspace',()=>({default:()=> <div>Unified engineering workspace (DOM shell fixture)</div>}));
vi.mock('./Viewport',()=>({default:({sample,selection}:any)=><div data-testid="viewport-surface" data-selection={selection}>{sample.position}</div>}));

let requests:{path:string;body:any}[]=[];
let failExperiment=false;
function state(status='REVIEWED'){const p=evidence.proposals.attempt_2;return {review_id:'a'.repeat(32),status,source_sha256:p.validation.proposed_sha256,validation:p.validation,verification:null,provenance:{kind:'recorded_genuine_model_proposal'},explanation:'Actual recorded proposal under fresh review',events:[]};}
beforeEach(()=>{
 requests=[];failExperiment=false;localStorage.clear();setToken('fixture-token');
 vi.stubGlobal('fetch',vi.fn(async(input:string,options?:RequestInit)=>{
  const url=new URL(input,'http://127.0.0.1:8765');const path=url.pathname;const body=options?.body?JSON.parse(String(options.body)):null;requests.push({path,body});
  let value:any;
  if(path==='/api/bootstrap')value=evidence.bootstrap;
  else if(path==='/api/agent/recorded')value=evidence.agent;
  else if(path==='/api/file')value=evidence.files[url.searchParams.get('path')!];
  else if(path==='/api/proposal')value=evidence.proposals[url.searchParams.get('variant')!];
  else if(path==='/api/experiment'){
   if(failExperiment)return {ok:false,json:async()=>({error:'Recorded evidence missing or corrupt'})};
   value=evidence.experiments[url.searchParams.get('scenario')!];
  }else if(path==='/api/review')value=state();
  else if(path==='/api/review/source')value={original:evidence.files['robot/controller.py'].content,modified:evidence.proposals.attempt_2.source};
  else if(path==='/api/review/create')value={job_id:'test-job'};
  else if(path==='/api/job')value={status:'COMPLETED',result:{review_id:'a'.repeat(32)}};
  else if(path==='/api/agent/start')return {ok:false,json:async()=>({error:'Secure API credentials missing; no request made'})};
  else throw new Error('Unexpected request '+path);
  return {ok:true,json:async()=>value};
 }));
});
async function ready(){render(<App/>);fireEvent.click(await screen.findByText('Advanced workspaces'));const nav=await screen.findByRole('navigation',{name:'Workspace mode'});fireEvent.click(within(nav).getByRole('button',{name:'Studio'}));await screen.findByTestId('scene-position');}

describe('IDE interactions over exact recorded evidence',()=>{
 it('opens the real engineering mode as the starting workspace without a paid request',async()=>{render(<App/>);expect(await screen.findByText('Unified engineering workspace (DOM shell fixture)')).toBeInTheDocument();fireEvent.click(screen.getByText('Advanced workspaces'));const nav=await screen.findByRole('navigation',{name:'Workspace mode'});expect(within(nav).getByRole('button',{name:'Build'})).toHaveAttribute('aria-pressed','true');expect(requests.some(r=>r.path==='/api/agent/start')).toBe(false);});
 it('opens Studio without paid calls, with 601 measured states and actual source',async()=>{
  await ready();expect(screen.getByRole('button',{name:'Studio'})).toHaveAttribute('aria-pressed','true');
  expect(screen.getByText('1/601 measured states')).toBeInTheDocument();
  expect(requests.some(r=>r.path==='/api/agent/start'||r.path==='/api/review/create')).toBe(false);
  expect(screen.getByRole('button',{name:/rail_carriage.xml/})).toBeInTheDocument();
  expect(screen.getByTestId('scene-position')).toHaveTextContent(evidence.experiments.A.variants.original.samples[0].position.toFixed(4));
 });
 it('retains scenario, file tabs, manual drafts, timestamp and agent input across all modes',async()=>{
  await ready();const user=userEvent.setup();
  fireEvent.change(screen.getByRole('combobox',{name:'Scenario'}),{target:{value:'B'}});await waitFor(()=>expect(screen.getByText('3 kg')).toBeInTheDocument());
  fireEvent.change(screen.getByRole('slider',{name:'Measured timeline sample'}),{target:{value:'240'}});
  await user.click(screen.getByRole('button',{name:'Code'}));
  const editor=await screen.findByRole('textbox',{name:'Monaco draft surface (DOM test)'});
  expect(editor).toHaveValue(evidence.files['robot/controller.py'].content);
  fireEvent.change(editor,{target:{value:evidence.files['robot/controller.py'].content+'\n# local draft'}});
  expect(screen.getByText('UNSAVED LOCAL DRAFT · UNVALIDATED')).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'New live session'}));
  fireEvent.change(screen.getByRole('textbox',{name:'Describe the problem'}),{target:{value:'Explain the actual source'}});
  await user.click(screen.getByRole('button',{name:'Agent focus'}));
  expect(screen.getByRole('textbox',{name:'Describe the problem'})).toHaveValue('Explain the actual source');
  expect(screen.queryByTestId('scene-position')).not.toBeVisible();
  await user.click(screen.getByRole('button',{name:'Focus or restore agent'}));
  expect(screen.getByRole('button',{name:'Code'})).toHaveAttribute('aria-pressed','true');
  expect((screen.getByRole('textbox',{name:'Monaco draft surface (DOM test)'}) as HTMLTextAreaElement).value).toContain('# local draft');
  await user.click(screen.getByRole('button',{name:'Studio'}));
  expect(screen.getByTestId('playback-time')).toHaveTextContent('1.200');
  expect(screen.getByRole('combobox',{name:'Scenario'})).toHaveValue('B');
 });
 it('opens exact JSON, Python and read-only historical files',async()=>{
  await ready();const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:/configs\/bodybase.json/}));
  expect(await screen.findByRole('textbox',{name:'Monaco draft surface (DOM test)'})).toHaveValue(evidence.files['configs/bodybase.json'].content);
  await user.click(screen.getByRole('button',{name:/recording\/attempt_1\/controller.py/}));
  await waitFor(()=>expect(screen.getByRole('textbox',{name:'Monaco draft surface (DOM test)'})).toHaveValue(evidence.proposals.attempt_1.source));
  expect(screen.getByRole('textbox',{name:'Monaco draft surface (DOM test)'})).toHaveAttribute('readonly');
 });
 it('steps, scrubs and synchronizes the pose, telemetry and actual contact state',async()=>{
  await ready();const user=userEvent.setup();const samples=evidence.experiments.A.variants.original.samples;
  await user.click(screen.getByRole('button',{name:'Step forward'}));expect(screen.getByTestId('playback-time')).toHaveTextContent('0.005');
  await user.click(screen.getByRole('button',{name:'Step backward'}));expect(screen.getByTestId('playback-time')).toHaveTextContent('0.000');
  fireEvent.change(screen.getByRole('slider',{name:'Measured timeline sample'}),{target:{value:'300'}});
  expect(screen.getByTestId('viewport-surface')).toHaveTextContent(String(samples[300].position));
  expect(screen.getByTestId('scene-position')).toHaveTextContent(samples[300].position.toFixed(4));
  await user.click(screen.getByRole('tab',{name:'Telemetry'}));
  expect(screen.getByTestId('value-velocity')).toHaveTextContent(samples[300].velocity.toFixed(4));
  expect(screen.getByTestId('value-wall_clearance')).toHaveTextContent(samples[300].wall_clearance.toFixed(4));
  expect(screen.getAllByTestId('chart-cursor')).toHaveLength(4);
  await user.click(screen.getByRole('checkbox',{name:'Compare baseline / verified'}));
  expect(document.querySelectorAll('.comparison-path')).toHaveLength(4);
  await user.click(screen.getByRole('button',{name:'Jump to end'}));expect(screen.getByTestId('playback-time')).toHaveTextContent('3.000');
  await user.click(screen.getByRole('button',{name:'Restart playback'}));expect(screen.getByTestId('playback-time')).toHaveTextContent('0.000');
 });
 it('plays real samples and freezes after pause',async()=>{
  await ready();let callback:FrameRequestCallback|undefined;
  vi.stubGlobal('requestAnimationFrame',vi.fn((cb:FrameRequestCallback)=>{callback=cb;return 1;}));vi.stubGlobal('cancelAnimationFrame',vi.fn());
  vi.spyOn(performance,'now').mockReturnValue(0);fireEvent.click(screen.getByRole('button',{name:'Play recorded playback'}));
  act(()=>callback?.(510));
  const slider=screen.getByRole('slider',{name:'Measured timeline sample'});expect(Number((slider as HTMLInputElement).value)).toBe(evidence.experiments.A.variants.original.samples.findLastIndex((s:any)=>s.time<=.510));
  fireEvent.click(screen.getByRole('button',{name:'Pause recorded playback'}));const paused=(slider as HTMLInputElement).value;
  expect(cancelAnimationFrame).toHaveBeenCalled();expect((slider as HTMLInputElement).value).toBe(paused);
  expect(screen.getByTestId('scene-position')).toHaveTextContent(evidence.experiments.A.variants.original.samples[Number(paused)].position.toFixed(4));
 });
 it('selects actual hierarchy objects and preserves layout resize/collapse state',async()=>{
  await ready();const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Scene'}));
  await user.click(screen.getByRole('button',{name:/G wall geom/}));
  expect(screen.getByTestId('viewport-surface')).toHaveAttribute('data-selection','geom:5');
  expect(screen.getByText('SELECTION / wall')).toBeInTheDocument();
  const separator=screen.getByRole('separator',{name:'Resize explorer'});fireEvent.keyDown(separator,{key:'ArrowRight'});
  expect(JSON.parse(localStorage.getItem('embody-layout')!).left).toBe(248);
  await user.click(screen.getByRole('button',{name:'Toggle explorer'}));expect(screen.queryByRole('separator',{name:'Resize explorer'})).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Maximize or restore main panel'}));expect(screen.queryByRole('separator',{name:'Resize agent'})).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Reset layout'}));expect(screen.getByRole('separator',{name:'Resize explorer'})).toHaveAttribute('aria-valuenow','232');
 });
 it('shows both model proposals, exact source diff and distinct safety outcomes',async()=>{
  await ready();const user=userEvent.setup();await user.click(screen.getByRole('tab',{name:'Verification'}));
  fireEvent.change(screen.getByRole('combobox',{name:'Review proposal'}),{target:{value:'attempt_1'}});
  await waitFor(()=>expect(screen.getByText(evidence.proposals.attempt_1.validation.explanation)).toBeInTheDocument());
  await user.click(screen.getByRole('button',{name:'Open Monaco diff'}));
  expect(await screen.findByTestId('diff-source')).toHaveTextContent(evidence.proposals.attempt_1.source.split('\n')[0]);
  expect(screen.getByTestId('diff-source').textContent).toContain(evidence.files['robot/controller.py'].content);
  expect(screen.getByTestId('diff-source').textContent).toContain(evidence.proposals.attempt_1.source);
 });
 it('opens the matching exact proposal from the recorded agent without starting an action',async()=>{
  await ready();const user=userEvent.setup();
  await user.click(screen.getAllByRole('button',{name:'Open diff'})[0]);
  await waitFor(()=>expect(screen.getByTestId('diff-source').textContent).toContain(evidence.proposals.attempt_1.source));
  await user.click(screen.getAllByRole('button',{name:'Open diff'})[1]);
  await waitFor(()=>expect(screen.getByTestId('diff-source').textContent).toContain(evidence.proposals.attempt_2.source));
  expect(requests.some(r=>r.path==='/api/agent/start'||r.path==='/api/review/create'||r.path==='/api/review/action')).toBe(false);
 });
 it('keeps recorded inference separate and requires fresh paid user consent',async()=>{
  await ready();const user=userEvent.setup();expect(screen.getByText('RECORDED · GPT-5.4 · DAY 4B.2')).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'New live session'}));
  const send=screen.getByRole('button',{name:'Start genuine agent session'});expect(send).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox',{name:'Describe the problem'}),{target:{value:'Read my real controller'}});
  expect(send).toBeDisabled();
  await user.click(screen.getByRole('checkbox',{name:/I authorize this new GPT/}));await user.click(send);
  await screen.findByRole('alert');expect(screen.getByText(/no automatic retry/)).toBeInTheDocument();
  expect(requests.filter(r=>r.path==='/api/agent/start')).toHaveLength(1);
  expect(requests.find(r=>r.path==='/api/agent/start')!.body.confirmation).toBe(evidence.bootstrap.live_policy.consent);
 });
 it('fails visibly for missing evidence rather than showing substitute results',async()=>{
  failExperiment=true;await readyWithoutScene();expect(screen.getByRole('alert')).toHaveTextContent('Recorded evidence missing or corrupt');
  expect(screen.queryByTestId('scene-position')).not.toBeInTheDocument();
 });
 it('labels absent model output as local status, never invented model speech',async()=>{
  await ready();const originalFetch=fetch;vi.stubGlobal('fetch',vi.fn(async(input:string,options?:RequestInit)=>{
   if(input==='/api/agent/start')return {ok:true,json:async()=>({job_id:'empty-output'})};
   if(input==='/api/job?id=empty-output')return {ok:true,json:async()=>({status:'COMPLETED',result:{orchestration_status:'ERROR',model_final_text:'',api_budget:{measured_cost_usd:'0',accounted_cost_usd:'0'},events:[],review_ids:[]}})};
   return originalFetch(input,options);
  }));
  const user=userEvent.setup();await user.click(screen.getByRole('button',{name:'New live session'}));
  fireEvent.change(screen.getByRole('textbox',{name:'Describe the problem'}),{target:{value:'Developer UI fixture; transport is mocked'}});
  await user.click(screen.getByRole('checkbox',{name:/I authorize this new GPT/}));await user.click(screen.getByRole('button',{name:'Start genuine agent session'}));
  await screen.findByText('LOCAL SESSION STATUS');expect(screen.queryByText('GENUINE LIVE MODEL OUTPUT')).not.toBeInTheDocument();
 });
});
async function readyWithoutScene(){render(<App/>);await screen.findByRole('alert');}

it('separates review, VM consent, permanent apply and rollback controls',async()=>{
 const user=userEvent.setup();render(<PatchReview proposal={evidence.proposals.attempt_2} variant="attempt_2" resumeId={'a'.repeat(32)} onDiff={vi.fn()} onReview={vi.fn()} errorReport={vi.fn()}/>);
 await screen.findByText('Current review: REVIEWED');
 expect(screen.getByRole('button',{name:'Verify in isolated VM'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Apply managed source'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Revert applied source'})).toBeDisabled();
 await user.click(screen.getByRole('checkbox',{name:/Approve A\/B\/C execution/}));
 expect(screen.getByRole('button',{name:'Verify in isolated VM'})).toBeEnabled();
 expect(screen.getByRole('button',{name:'Apply managed source'})).toBeDisabled();
 expect(requests.every(r=>r.path!=='/api/review/action')).toBe(true);
});

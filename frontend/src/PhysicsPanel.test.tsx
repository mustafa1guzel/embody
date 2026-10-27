import fixtureRaw from '../test/physics.json?raw';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import PhysicsPanel from './PhysicsPanel';
import App from './App';
import evidenceRaw from '../test/recorded-study.public.json?raw';
vi.mock('./Editor',()=>({default:()=> <div>DOM test editor surface</div>}));
vi.mock('./Viewport',()=>({default:()=> <div>DOM test viewport surface</div>}));
const fixture=JSON.parse(fixtureRaw).reports;
beforeEach(()=>{
 vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
  const q=new URL(path,'http://127.0.0.1').searchParams;
  return {ok:true,json:async()=>fixture[q.get('scenario')+'_'+q.get('variant')]};
 }));
});
it('renders actual deterministic bounds separately from genuine recorded safety and unknown program proof',async()=>{
 render(<PhysicsPanel scenario="A" variant="attempt_2"/>);
 expect((await screen.findAllByText('CONDITIONALLY_FEASIBLE')).length).toBe(2);
 expect(screen.getByText('0.36 m')).toBeInTheDocument();
 expect(screen.getByText('0.0524 / 0.0024 m')).toBeInTheDocument();
 expect(screen.getByText(/Program proof:/)).toHaveTextContent('UNKNOWN');
 expect(screen.getByText(/Recorded safety:/)).toHaveTextContent('PASS');
 expect(screen.getByText(/Analysis grants no VM or apply approval/)).toBeInTheDocument();
 expect(screen.queryByRole('button')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Physical metrics and calculation methods'));
 expect(screen.getAllByText('NOT_AVAILABLE').length).toBeGreaterThan(0);
 expect(screen.getByText('signed mechanical work').nextElementSibling).toHaveTextContent('-1.428 J');
});
it('reloads selected scenario and candidate without any execution or approval POST',async()=>{
 const view=render(<PhysicsPanel scenario="A" variant="original"/>);
 await screen.findByText('PROVEN_INFEASIBLE');
 expect(screen.getByText(/Recorded safety:/)).toHaveTextContent('FAIL');
 view.rerender(<PhysicsPanel scenario="B" variant="attempt_2"/>);
 await screen.findByText('0.54 m');
 expect(fetch).toHaveBeenCalledTimes(2);
 expect(fetch).toHaveBeenLastCalledWith('/api/physics?scenario=B&variant=attempt_2',undefined);
});
it('shows explicit BLOCKED on evidence failure and removes prior PASS',async()=>{
 const view=render(<PhysicsPanel scenario="A" variant="attempt_2"/>);await screen.findByText('0.36 m');
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>({error:'Recorded model hash mismatch'})})));
 view.rerender(<PhysicsPanel scenario="B" variant="attempt_2"/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('BLOCKED');
 expect(screen.queryByText('PASS',{exact:true})).not.toBeInTheDocument();
});
it('rejects a different report identity without showing its verdict',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>fixture.A_attempt_2})));
 render(<PhysicsPanel scenario="C" variant="original"/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('identity or schema mismatch');
});
it('ignores an older response arriving after a scenario change',async()=>{
 let resolve:(value:unknown)=>void=()=>{};
 vi.stubGlobal('fetch',vi.fn().mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValueOnce({ok:true,json:async()=>fixture.C_attempt_2}));
 const view=render(<PhysicsPanel scenario="A" variant="original"/>);
 view.rerender(<PhysicsPanel scenario="C" variant="attempt_2"/>);
 await screen.findByText('0.25 m');
 await act(async()=>{resolve({ok:true,json:async()=>fixture.A_original});});
 await waitFor(()=>expect(screen.queryByText('PROVEN_INFEASIBLE')).not.toBeInTheDocument());
 expect(screen.getByText('0.25 m')).toBeInTheDocument();
});
it('blocks an unsupported generic analytical PASS instead of presenting a controller certificate',async()=>{
 const value=structuredClone(fixture.A_attempt_2);value.analytical_feasibility.status='PASS';
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>value})));
 render(<PhysicsPanel scenario="A" variant="attempt_2"/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('BLOCKED');
 expect(screen.queryByText('PASS',{exact:true})).not.toBeInTheDocument();
});
it('opens the Physics dock through the real App and follows scenario selection using GET requests only',async()=>{
 const evidence=JSON.parse(evidenceRaw);localStorage.clear();
 vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
  const u=new URL(path,'http://127.0.0.1');let value;
  if(u.pathname==='/api/bootstrap')value=evidence.bootstrap;
  else if(u.pathname==='/api/agent/recorded')value=evidence.agent;
  else if(u.pathname==='/api/file')value=evidence.files[u.searchParams.get('path')!];
  else if(u.pathname==='/api/proposal')value=evidence.proposals[u.searchParams.get('variant')!];
  else if(u.pathname==='/api/experiment')value=evidence.experiments[u.searchParams.get('scenario')!];
  else if(u.pathname==='/api/physics')value=fixture[u.searchParams.get('scenario')+'_'+u.searchParams.get('variant')];
  else throw new Error('Unexpected request '+path);
  return {ok:true,json:async()=>value};
 }));
 render(<App/>);fireEvent.click(await screen.findByRole('button',{name:'Studio'}));fireEvent.click(await screen.findByRole('tab',{name:'Physics'}));
 await screen.findByText('0.36 m');
 fireEvent.change(screen.getByRole('combobox',{name:'Scenario'}),{target:{value:'B'}});
 await screen.findByText('0.54 m');
 expect(screen.getByRole('button',{name:'Studio'})).toHaveAttribute('aria-pressed','true');
 expect(vi.mocked(fetch).mock.calls.every(call=>call[1]===undefined)).toBe(true);
});

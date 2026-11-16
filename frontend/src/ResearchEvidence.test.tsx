import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import ResearchEvidence from './ResearchEvidence';
import EfficiencyBenchmarks from './research/EfficiencyBenchmarks';
import type {Read,View} from './research/types';
import {api} from './api';
vi.mock('./api',()=>({api:vi.fn()}));
const calls:string[]=[];
const read={project:{id:'a'.repeat(32)},sha256:'b'.repeat(64),stale:false} as Read;
const view={campaign:{id:'c'.repeat(32),batches:[]},records:[],summaries:[],evidence_completeness:{referenced_cases_currently_known:0,available_verified_cases:0,unknown_missing_case_count:true,references:[{reference:'missing',availability:'MISSING',cases:0,errors:['Raw trajectory unavailable']}]}} as unknown as View;
const catalog={bundles:[],external:[],historical_missing:[{id:'v04_private_three_case_demo',availability:'MISSING',reason:'Raw directory unavailable; screenshots are not measurements'}],limits:{},limitations:[]};
beforeEach(()=>{calls.length=0;vi.mocked(api).mockReset();vi.mocked(api).mockImplementation(async(path)=>{calls.push(path);if(path==='research-evidence/catalog')return structuredClone(catalog) as never;if(path==='research-benchmarks/catalog')return {runs:[]} as never;throw new Error('Unexpected route '+path);});});
it('shows actual missing evidence and never loads physics or models',async()=>{
 render(<ResearchEvidence read={read} view={view} onLinked={vi.fn()} onGraph={vi.fn()}/>);await screen.findByText(/Raw directory unavailable/);
 expect(screen.getByText(/Missing references have unknown case cardinality/)).toBeInTheDocument();expect(screen.getByRole('button',{name:'Capture selected evidence bundle'})).toBeDisabled();expect(calls).toEqual(['research-evidence/catalog']);
});
it('preserves genuine saved source distinctions and graph navigation',async()=>{
 const graph=vi.fn();render(<ResearchEvidence read={read} view={view} onLinked={vi.fn()} onGraph={graph}/>);await screen.findByText(/Raw directory unavailable/);fireEvent.click(screen.getByRole('button',{name:'Inspect supporting evidence graph'}));expect(graph).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByText('Verify or import a portable package'));expect(screen.getByRole('button',{name:'Import as EXTERNAL_UNVERIFIED'})).toBeDisabled();expect(screen.getByText(/Valid hashes do not prove MuJoCo origin/)).toBeInTheDocument();
});
it('displays verification rejection without a stale success badge',async()=>{
 vi.mocked(api).mockRejectedValue(new Error('Required replay missing'));render(<ResearchEvidence read={read} view={view} onLinked={vi.fn()} onGraph={vi.fn()}/>);expect(await screen.findByRole('alert')).toHaveTextContent('Required replay missing');expect(screen.queryByText('VERIFIED_AVAILABLE')).not.toBeInTheDocument();
});
it('renders equal-budget computed comparisons with explicit offline provenance',async()=>{
 const old=vi.mocked(api).getMockImplementation()!;const result={id:'d'.repeat(32),environment:{id:'single_transition',dimension:1,domain:[[0,1]],definition:'u >= .37',provenance:'SYNTHETIC_ALGORITHM_FIXTURE'},config:{budget:12,seed:1,resolution:.005},runs:[{strategy:'adaptive',history:[{query:1,point:[0],outcome:'ORACLE_FAIL',rationale:'Counted endpoint'}],rounds:[{queries:1,smallest_observed_width:null,intervals:[]}],metrics:{evaluated_points:1,queries_to_target:null,termination:'QUERY_BUDGET_EXHAUSTED'}}],limitations:['No measured advantage claimed']};
 vi.mocked(api).mockImplementation(async(path,body)=>path==='research-benchmarks/run'?(calls.push(path),structuredClone(result) as never):old(path,body));
 render(<EfficiencyBenchmarks projectId={read.project.id} campaignId={view.campaign.id}/>);await waitFor(()=>expect(calls).toContain('research-benchmarks/catalog'));expect(calls).not.toContain('research-benchmarks/run');fireEvent.click(screen.getByRole('button',{name:'Run bounded offline comparison'}));await screen.findByText(/single_transition · SYNTHETIC_ALGORITHM_FIXTURE/);expect(screen.getByText('Not reached / unavailable')).toBeInTheDocument();expect(screen.getByRole('img',{name:'Offline queried points by strategy'})).toBeInTheDocument();expect(calls.some(p=>p.includes('rail-sweeps/start'))).toBe(false);
});
it('rejects stale asynchronous evidence results on unmount',async()=>{
 let resolve!:(x:unknown)=>void;vi.mocked(api).mockImplementation(()=>new Promise(r=>{resolve=r;}) as never);const onLinked=vi.fn();const component=render(<ResearchEvidence read={read} view={view} onLinked={onLinked} onGraph={vi.fn()}/>);component.unmount();await act(async()=>resolve(catalog));expect(onLinked).not.toHaveBeenCalled();
});

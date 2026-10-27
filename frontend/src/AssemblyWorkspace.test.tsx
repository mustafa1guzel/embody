/** Explicit offline API/view doubles, not native physics or live model evidence. */
import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import reviewRaw from '../test/assembly_review.json?raw';
import pendingRaw from '../test/assembly_pending.json?raw';
import AssemblyWorkspace from './AssemblyWorkspace';
const {call,view,jobCall}=vi.hoisted(()=>({call:vi.fn(),view:vi.fn(),jobCall:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args),job:(...args:unknown[])=>jobCall(...args)}));
vi.mock('./WorldViewport',()=>({default:(props:any)=>{view(props);return <div data-testid="assembly-view-double"/>;}}));
const fixture=JSON.parse(reviewRaw),pending=JSON.parse(pendingRaw);
beforeEach(()=>{call.mockReset();view.mockClear();jobCall.mockReset();call.mockResolvedValue(structuredClone(fixture));});
it('separates measured physical failure feedback from compilation and shows axes without an automatic repair',async()=>{
 const b=structuredClone(fixture);b.review.provenance={physical_failure_feedback:{status:'PHYSICAL_FAILURE',detected_stage:'NATIVE_SIMULATION',construction_status:'VALID_COMPILED',measured_signed_forward_displacement_m:-.018516,required_direction:{minimum_signed_displacement_m:.005},contacts:{wheel_ground_pair_observations:1456,unexpected_contact_count:0},wheels:[{joint_body_id:'explicit_mock_joint',placement:'rear_left',initial_native_axis_world:[0,-1,0],actuator:{command:.012},ideal_forward_m_per_positive_joint_rad:-.035,final_joint_rate_rad_s:1,measured_wheel_ground_pair_observations:200}]}};call.mockResolvedValue(b);
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByTestId('assembly-physical-feedback');expect(screen.getByTestId('assembly-physical-feedback')).toHaveTextContent('PHYSICAL_FAILURE · NATIVE_SIMULATION');expect(screen.getByTestId('assembly-physical-feedback')).toHaveTextContent('-0.018516 m');expect(screen.getByRole('table',{name:'Measured wheel direction feedback'})).toHaveTextContent('[0,-1,0]');expect(screen.getByRole('button',{name:'Apply reviewed assembly'})).toBeDisabled();expect(jobCall).not.toHaveBeenCalled();expect(call.mock.calls.every(c=>c[0]==='engineering/assembly/bootstrap')).toBe(true);
});
it('displays supplied signed forward measurement without treating backward distance as forward',async()=>{
 const b=structuredClone(fixture);b.review.provenance={directional_acceptance:{signed_forward_displacement_m:-.02,status:'FAIL'}};
 // Explicit view double, never native physics or model evidence.
 b.review.native={status:'OFFLINE_VIEW_DOUBLE',result:{samples:[{time_s:0}],independent_verification:{status:'NOT_PHYSICS_EVIDENCE'},contract:{}},observations:{horizontal_displacement_m:.02,wheel_ground_contact_events:0,unexpected_contacts:[],checks:{}}};call.mockResolvedValue(b);
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByTestId('assembly-forward-evidence');expect(screen.getByTestId('assembly-forward-evidence')).toHaveTextContent('-0.020000 m · FAIL');expect(screen.getByTestId('assembly-forward-evidence')).toHaveTextContent('required ≥0.005 m');expect(jobCall).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Apply reviewed assembly'})).toBeDisabled();
});
it('shows actual empty head and explicitly offline unbuilt copied plan',async()=>{
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByTestId('assembly-origin');expect(screen.getByTestId('assembly-origin')).toHaveTextContent('OFFLINE_PROTOCOL_FIXTURE');
 expect(screen.getByTestId('assembly-authoritative-status')).toHaveTextContent('HEAD r0 · 0 ShapeSpecs');expect(screen.getByTestId('assembly-proposal-status')).toHaveTextContent('aggregate proposed r1');
 expect(screen.getByRole('table',{name:'Assembly parts and dimensions'}).querySelectorAll('tbody tr')).toHaveLength(9);
 expect(screen.getByRole('button',{name:'Apply reviewed assembly'})).toBeDisabled();expect(screen.getByRole('checkbox',{name:'Approve reviewed assembly'})).toBeDisabled();
 expect(view.mock.calls.at(-1)![0].world.objects).toHaveLength(19);expect(view.mock.calls.at(-1)![0].readOnly).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'View current empty project'}));expect(view.mock.calls.at(-1)![0].world.objects).toHaveLength(1);
 expect(jobCall).not.toHaveBeenCalled();expect(call.mock.calls.every(c=>c[0]==='engineering/assembly/bootstrap')).toBe(true);
});
it('pending approval does not display a fabricated model plan',async()=>{
 call.mockResolvedValue(pending);render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByText('PENDING_APPROVAL — no live AI assembly generated');expect(screen.queryByRole('table',{name:'Assembly parts and dimensions'})).not.toBeInTheDocument();expect(jobCall).not.toHaveBeenCalled();
});
it('manual editing invalidates the old proposal without mutating head',async()=>{
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByTestId('assembly-proposal-status');fireEvent.click(screen.getByText('Inspect or edit exact AssemblyPlan JSON',{exact:true}));fireEvent.change(screen.getByRole('textbox',{name:'AssemblyPlan JSON'}),{target:{value:'{}'}});expect(screen.queryByTestId('assembly-proposal-status')).not.toBeInTheDocument();expect(call.mock.calls.every(c=>c[0]==='engineering/assembly/bootstrap')).toBe(true);
});
it('shows actual receipt fields only when supplied, without inventing provider output',async()=>{
 const b=structuredClone(fixture);b.review.origin='GENUINE_PROVIDER_RESPONSE';b.review.provenance={usage_cost_receipt:{measured_cost_usd:'0.0123',accounted_cost_usd:'0.0123'}};call.mockResolvedValue(b);
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByText('Genuine provider response — actual returned action plan');expect(screen.getByTestId('assembly-cost')).toHaveTextContent('0.0123');
});
it('distinguishes immutable historical error from current semantic analysis and raw rejected plan',async()=>{
 const b=structuredClone(pending);b.review={origin:'GENUINE_PROVIDER_RESPONSE',status:'FAIL',proposal:null,native:null,failure:{reason:'Original run failed'}};
 b.rejections=[{failure_id:'original_failure',original:{origin:'MODEL_TOOL_UNTRUSTED_ASSEMBLY',error:{message:'Original frozen reference error'},plan:{goal:'Unchanged rejected model goal',steps:[]}},analysis_label:'Current read-only semantic analysis; historical error unchanged.',current_analysis:{status:'SEMANTIC_PREFLIGHT_FAIL',errors:1,diagnostics:[{code:'WRONG_ID_NAMESPACE',step_id:'mounts',operation_index:0,field:'target',actual:'mount_body',expected:'part_id',message:'target requires an owning ShapeSpec part ID.'}]}}];
 call.mockResolvedValue(b);render(<AssemblyWorkspace onRefresh={vi.fn()}/>);
 await screen.findByTestId('assembly-rejected-plans');expect(screen.getByText('Original frozen reference error',{exact:false})).toBeInTheDocument();expect(screen.getByText('WRONG_ID_NAMESPACE')).toBeInTheDocument();
 expect(screen.getByText('Unchanged rejected model goal',{exact:false})).toBeInTheDocument();expect(screen.queryByRole('table')).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'Apply reviewed assembly'})).not.toBeInTheDocument();expect(jobCall).not.toHaveBeenCalled();
});
it('renders structured live validation rejection without silently fixing editor input',async()=>{
 call.mockResolvedValueOnce(structuredClone(pending)).mockRejectedValueOnce(Object.assign(new Error('Rejected'),{diagnostics:[{code:'CHILD_FRAME_MISSING',step_id:'s',operation_index:1,field:'frame_id',actual:'parent_datum',expected:['origin'],message:'Use a frame on the child part.'}]}));
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByTestId('assembly-origin');const editor=screen.getByRole('textbox',{name:'AssemblyPlan JSON'});fireEvent.change(editor,{target:{value:'{"invalid":"unchanged"}'}});fireEvent.click(screen.getByRole('button',{name:'Validate assembly plan'}));
 await screen.findByTestId('assembly-current-diagnostics');expect(screen.getByText('CHILD_FRAME_MISSING')).toBeInTheDocument();expect(editor).toHaveValue('{"invalid":"unchanged"}');expect(jobCall).not.toHaveBeenCalled();
});
it('shows whole-plan mass allocation without implying a native pass or applying',async()=>{
 call.mockResolvedValueOnce(structuredClone(pending)).mockResolvedValueOnce({status:'REJECTED',stages:{schema_dag:'PASS',declarations:'FAIL'},native:'NOT_EXECUTED',total_mass_kg:2.45,mass_limit_kg:2,mass_allocation:[{body_id:'root',mass_kg:.2,source:'EXISTING_PRIMITIVE_DEFAULT',parent_body_id:null}],diagnostics:[{code:'TOTAL_MASS',field:'total_mass_kg',actual:2.45,expected:2,message:'Total exceeds envelope.'}]});
 render(<AssemblyWorkspace onRefresh={vi.fn()}/>);await screen.findByTestId('assembly-origin');fireEvent.change(screen.getByRole('textbox',{name:'AssemblyPlan JSON'}),{target:{value:'{"unchanged":"input"}'}});fireEvent.click(screen.getByRole('button',{name:'Assess entire assembly'}));
 await screen.findByTestId('assembly-engineering-assessment');expect(screen.getByText('TOTAL_MASS')).toBeInTheDocument();expect(screen.getByText('EXISTING_PRIMITIVE_DEFAULT')).toBeInTheDocument();expect(screen.getByText(/2.450000 kg \/ 2 kg/)).toBeInTheDocument();expect(screen.getByRole('textbox',{name:'AssemblyPlan JSON'})).toHaveValue('{"unchanged":"input"}');expect(jobCall).not.toHaveBeenCalled();expect(call.mock.calls[1][0]).toBe('engineering/assembly/assess');
});

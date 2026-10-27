/** Deterministic UI protocol doubles; no mocked physics or AI success claim. */
import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import raw from '../test/shapebase.json?raw';import proposed from '../test/shapebase_proposal.json?raw';
import ShapeWorkspace from './ShapeWorkspace';
const {call,views}=vi.hoisted(()=>({call:vi.fn(),views:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args),job:vi.fn()}));
vi.mock('./WorldViewport',()=>({default:(props:any)=>{views(props);return <div data-testid="shape-view-double">{props.readOnly?'READ_ONLY':'EDITABLE'}</div>;}}));
const fixture=JSON.parse(raw),proposal=JSON.parse(proposed);
beforeEach(()=>{call.mockReset();views.mockClear();call.mockImplementation(async(path:string)=>{if(path==='engineering/shape_agent_review')return {status:'NO_SESSION'};if(path==='engineering/propose')return structuredClone(proposal);if(path==='engineering/decide')return {project:proposal.proposed_project};throw new Error('Unexpected fixture path');});});
it('parameter fields remain draft until typed validation and separate explicit apply',async()=>{
 const refresh=vi.fn(async()=>fixture);render(<ShapeWorkspace boot={fixture} onRefresh={refresh}/>);
 const input=await screen.findByRole('spinbutton',{name:'Shape Length (m)'});fireEvent.change(input,{target:{value:'0.42'}});
 expect(views.mock.calls.at(-1)![0].world).toEqual(fixture.project.world);expect(screen.getByTestId('shape-application-status')).toHaveTextContent('CURRENT AUTHORITATIVE');
 fireEvent.click(screen.getByRole('button',{name:'Preview shape change'}));await screen.findByText(/PROPOSED_NOT_APPLIED/);
 expect(call).toHaveBeenCalledWith('engineering/propose',expect.objectContaining({expected_revision:4,operations:[{kind:'update_shape_parameter',target:'shape_link_one',parameter:'length_m',value:.42}]}));
 expect(views.mock.calls.at(-1)![0].readOnly).toBe(true);expect(screen.getByRole('button',{name:'Apply reviewed shape data'})).toBeDisabled();expect(refresh).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'View current shape'}));expect(views.mock.calls.at(-1)![0].world).toEqual(fixture.project.world);
 fireEvent.click(screen.getByRole('button',{name:'View proposed shape'}));expect(views.mock.calls.at(-1)![0].world).toEqual(proposal.proposed_project.world);
 fireEvent.click(screen.getByRole('checkbox',{name:'Approve reviewed shape data'}));fireEvent.click(screen.getByRole('button',{name:'Apply reviewed shape data'}));
 await waitFor(()=>expect(refresh).toHaveBeenCalledOnce());expect(call).toHaveBeenCalledWith('engineering/decide',expect.objectContaining({decision:'apply',confirmation:'APPLY REVIEWED ENGINEERING CHANGE'}));
});
it('editing a prepared proposal invalidates the approval and preview',async()=>{
 render(<ShapeWorkspace boot={fixture} onRefresh={vi.fn()}/>);fireEvent.change(await screen.findByRole('spinbutton',{name:'Shape Length (m)'}),{target:{value:'0.42'}});fireEvent.click(screen.getByRole('button',{name:'Preview shape change'}));await screen.findByRole('checkbox',{name:'Approve reviewed shape data'});fireEvent.click(screen.getByRole('checkbox',{name:'Approve reviewed shape data'}));
 fireEvent.change(screen.getByRole('spinbutton',{name:'Shape Length (m)'}),{target:{value:'0.44'}});expect(screen.queryByRole('button',{name:'Apply reviewed shape data'})).not.toBeInTheDocument();expect(screen.getByTestId('shape-application-status')).toHaveTextContent('CURRENT AUTHORITATIVE');
});
it('invalid proposal errors remain visible without changing the current geometry',async()=>{
 call.mockRejectedValue(new Error('Mounting hole outside part boundary'));
 render(<ShapeWorkspace boot={fixture} onRefresh={vi.fn()}/>);fireEvent.change(await screen.findByRole('spinbutton',{name:'Hole mount_a u'}),{target:{value:'0.49'}});fireEvent.click(screen.getByRole('button',{name:'Preview shape change'}));await screen.findByRole('alert');expect(screen.queryByRole('button',{name:'Apply reviewed shape data'})).not.toBeInTheDocument();expect(views.mock.calls.at(-1)![0].world).toEqual(fixture.project.world);
});
it('loads explicitly labelled offline proposal and forbids experiment application',async()=>{
 call.mockImplementation(async(path:string)=>{if(path==='engineering/shape_agent_review')return {status:'OFFLINE_VALIDATED',origin:'OFFLINE_PROTOCOL_FIXTURE',task:'Make the first link longer',project_revision:4,project_sha256:fixture.identities.project,proposal,validation:{status:'PASS'}};throw new Error('No mutation permitted');});
 render(<ShapeWorkspace boot={fixture} onRefresh={vi.fn()}/>);await screen.findByText(/OFFLINE_PROTOCOL_FIXTURE/);
 expect(screen.getByRole('table',{name:'Original and proposed shape dimensions'})).toHaveTextContent('0.30.42');
 fireEvent.click(screen.getByRole('button',{name:'Inspect agent shape proposal'}));
 expect(screen.getByRole('button',{name:'Apply reviewed shape data'})).toBeDisabled();expect(screen.getByRole('checkbox',{name:'Approve reviewed shape data'})).toBeDisabled();expect(screen.getByRole('button',{name:'Run native proxy check'})).toBeDisabled();
 expect(views.mock.calls.at(-1)![0].world).toEqual(proposal.proposed_project.world);expect(call.mock.calls.every(c=>c[0]==='engineering/shape_agent_review')).toBe(true);
});
it('shows pending live authorization without claiming a model decision',async()=>{
 call.mockResolvedValue({status:'PENDING_APPROVAL',origin:'NO_MODEL_REQUEST',task:'Natural language task',project_revision:4,project_sha256:fixture.identities.project});
 render(<ShapeWorkspace boot={fixture} onRefresh={vi.fn()}/>);await screen.findByText('PENDING_APPROVAL');expect(screen.getByText('No paid model request or model proposal yet.')).toBeInTheDocument();expect(screen.queryByRole('button',{name:'Inspect agent shape proposal'})).not.toBeInTheDocument();
});
it('does not label a failed live attempt without a response as genuine model output',async()=>{
 call.mockResolvedValue({status:'FAIL',origin:'NO_PROVIDER_RESPONSE',task:'Task',project_revision:4,project_sha256:fixture.identities.project,failure:{reason:'Credentials unavailable'}});
 render(<ShapeWorkspace boot={fixture} onRefresh={vi.fn()}/>);await screen.findByText('No usable provider response; inspect the request ledger and failure.');expect(screen.queryByText('Genuine provider response — review only')).not.toBeInTheDocument();expect(screen.getByRole('alert')).toHaveTextContent('Credentials unavailable');
});

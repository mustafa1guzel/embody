import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import raw from '../test/shapebase.json?raw';import proposed from '../test/shapebase_proposal.json?raw';
import PropertyEditor,{editableFields,propertyOperation} from './PropertyEditor';
import {initialWorkspace,workspaceReducer,representation} from './workspaceState';
const {call}=vi.hoisted(()=>({call:vi.fn()}));vi.mock('./api',()=>({api:(...a:unknown[])=>call(...a)}));
const b=JSON.parse(raw),q=JSON.parse(proposed),shape=b.project.shape_specs[0],body=b.project.world.objects.find((o:any)=>o.id===shape.body_id);
beforeEach(()=>{call.mockReset();});
function view(enabled=true,onProposal=vi.fn()){render(<PropertyEditor project={b.project} sha={b.identities.project} body={body} shape={shape} enabled={enabled} onProposal={onProposal}/>);return onProposal;}
it('sends exact part ID and SI value through existing proposal API; no decision or simulation',async()=>{
 call.mockResolvedValue(q);const accept=view();fireEvent.change(screen.getByRole('combobox',{name:'Editable property'}),{target:{value:'shape:length_m'}});fireEvent.change(screen.getByRole('spinbutton',{name:'Property value'}),{target:{value:'.42'}});
 expect(call).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Review change'}));await waitFor(()=>expect(accept).toHaveBeenCalledWith(q));
 expect(call).toHaveBeenCalledExactlyOnceWith('engineering/propose',expect.objectContaining({expected_revision:b.project.revision,expected_sha256:b.identities.project,operations:[{kind:'update_shape_parameter',target:shape.id,parameter:'length_m',value:.42}]}));
});
it('keeps backend validation failure visible and cancel restores current value without an apply',async()=>{
 call.mockRejectedValue(new Error('Mounting hole outside supported boundary'));view();fireEvent.change(screen.getByRole('spinbutton',{name:'Property value'}),{target:{value:'-1'}});fireEvent.click(screen.getByRole('button',{name:'Review change'}));expect(await screen.findByRole('alert')).toHaveTextContent('Change rejected');expect(screen.getByRole('alert')).toHaveTextContent('Project unchanged');fireEvent.click(screen.getByRole('button',{name:'Cancel edit'}));expect(screen.queryByRole('alert')).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Review change'})).toBeDisabled();expect(call.mock.calls).toHaveLength(1);
});
it('canceling an unsubmitted draft never requests any backend action',()=>{view();fireEvent.change(screen.getByRole('spinbutton',{name:'Property value'}),{target:{value:'.5'}});fireEvent.click(screen.getByRole('button',{name:'Cancel edit'}));expect(call).not.toHaveBeenCalled();});
it('historical, saved and proposed views expose no editing controls',()=>{view(false);expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();expect(screen.getByText(/Read-only representation/)).toBeInTheDocument();expect(call).not.toHaveBeenCalled();});
it('does not expose generic transforms for registered mounts or geometry for protected shape bodies',()=>{
 const elbow=b.project.world.objects.find((o:any)=>o.id==='elbow');expect(editableFields(b.project,elbow).some(f=>f.key.startsWith('position'))).toBe(false);
 expect(editableFields(b.project,body,shape).every(f=>f.key.startsWith('shape:'))).toBe(true);
 expect(()=>propertyOperation(body,shape,'shape:does_not_exist',.1)).toThrow();expect(()=>propertyOperation(body,shape,'mass',Infinity)).toThrow();
 expect(propertyOperation(elbow,undefined,'mass',.07)).toEqual({kind:'set_mass',target:'elbow',mass_kg:.07});
});
it('local change state requires matching current base and uses only server-regenerated geometry; discard restores head',()=>{
 const data:any={snapshot:{key:'current',historical:false,editable:true,project:b.project,project_sha256:b.identities.project,runs:[],proposals:[],shape_parts:b.shapebase.parts},projects:[],policy:{}};
 const initial=workspaceReducer(initialWorkspace,{type:'open',data});const s=workspaceReducer(initial,{type:'change',change:q});expect(s.view).toBe('change');expect(representation(s).project).toEqual(q.proposed_project);expect(data.snapshot.project).toEqual(b.project);
 const discarded=workspaceReducer(s,{type:'discard'});expect(discarded.change).toBeNull();expect(representation(discarded).project).toEqual(b.project);
 expect(workspaceReducer(initial,{type:'change',change:{...q,base_project_sha256:'wrong'}})).toBe(initial);
 expect(workspaceReducer({...initial,data:{...data,snapshot:{...data.snapshot,historical:true}}},{type:'change',change:q}).change).toBeNull();
});

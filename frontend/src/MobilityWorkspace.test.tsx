/** Deterministic UI transport/view doubles; native evidence is tested separately. */
import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import roverRaw from '../test/mobility_rover.json?raw';
import droneRaw from '../test/mobility_drone.json?raw';
import ShapeWorkspace from './ShapeWorkspace';
const {call,views}=vi.hoisted(()=>({call:vi.fn(),views:vi.fn()}));
vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args),job:vi.fn()}));
vi.mock('./WorldViewport',()=>({default:(props:any)=>{views(props);return <div data-testid="mobility-view-double"/>;}}));
const rover=JSON.parse(roverRaw),drone=JSON.parse(droneRaw);
beforeEach(()=>{call.mockReset();views.mockClear();call.mockImplementation(async(path:string)=>{if(path==='engineering/shape_agent_review')return {status:'NO_SESSION'};throw new Error('Deliberate stop before any server mutation');});});
it('wheel dimensions and explicit mobility limits appear without applying draft input',async()=>{
 render(<ShapeWorkspace boot={rover} initialBody="front_left_wheel" onRefresh={vi.fn()}/>);
 const field=await screen.findByRole('spinbutton',{name:'Shape Outer diameter (m)'});expect(field).toHaveValue(.12);expect(screen.getByTestId('mobility-scope')).toHaveTextContent('No suspension');
 fireEvent.change(field,{target:{value:'0.144'}});expect(views.mock.calls.at(-1)![0].world).toEqual(rover.project.world);
 fireEvent.click(screen.getByRole('button',{name:'Preview shape change'}));await screen.findByRole('alert');
 expect(call).toHaveBeenCalledWith('engineering/propose',expect.objectContaining({operations:[{kind:'update_shape_parameter',target:'shape_front_left_wheel',parameter:'outer_diameter_m',value:.144}]}));expect(call.mock.calls.some(c=>c[0]==='engineering/decide')).toBe(false);
});
it('four-arm length preview creates one explicit typed batch and leaves the head alone',async()=>{
 const refresh=vi.fn();render(<ShapeWorkspace boot={drone} initialBody="arm_east" onRefresh={refresh}/>);
 fireEvent.change(await screen.findByRole('spinbutton',{name:'Shape Length (m)'}),{target:{value:'0.24'}});fireEvent.click(screen.getByRole('button',{name:'Preview all four arm lengths'}));await screen.findByRole('alert');
 const args=call.mock.calls.find(c=>c[0]==='engineering/propose')![1];expect(args.operations).toHaveLength(4);expect(new Set(args.operations.map((o:any)=>o.target)).size).toBe(4);expect(args.operations.every((o:any)=>o.kind==='update_shape_parameter'&&o.parameter==='length_m'&&o.value===.24)).toBe(true);expect(refresh).not.toHaveBeenCalled();expect(views.mock.calls.at(-1)![0].world).toEqual(drone.project.world);
});
it('fixed attachment uses the existing proposal endpoint with exact mount fields',async()=>{
 render(<ShapeWorkspace boot={drone} initialBody="arm_east" onRefresh={vi.fn()}/>);
 fireEvent.click(await screen.findByText('Attach to an existing fixed mount',{exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Preview fixed mounting'}));await screen.findByRole('alert');
 expect(call).toHaveBeenCalledWith('engineering/propose',expect.objectContaining({operations:[{kind:'attach_part_to_mount',target:'shape_arm_east',mount_body_id:'arm_east_root',frame_id:'root'}]}));
});

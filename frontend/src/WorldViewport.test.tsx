import {expect,it,vi} from 'vitest';
import {render} from '@testing-library/react';
import type {World,WorldObject} from './engineeringTypes';
import WorldViewport,{worldGeometry} from './WorldViewport';
const {draw}=vi.hoisted(()=>({draw:vi.fn()}));
vi.mock('three',async original=>{const actual=await original<typeof import('three')>();return {...actual,WebGLRenderer:class {domElement=document.createElement('canvas');setClearColor(){}setPixelRatio(){}setSize(){}dispose(){}render=draw;}};});
const object:WorldObject={id:'beam',name:'Beam',parent:null,kind:'dynamic',geometry:'box',position_m:[0,0,.2],rotation_rad:[0,0,0],dimensions_m:[.4,.04,.02],mass_kg:.2,joint:{kind:'revolute',axis:[0,0,1],range:[0,1],initial_position:0,initial_velocity:0,damping:.01},actuator:null,contact:{enabled:true,friction:[.7,.005,.0001]},visual:{rgba:[.3,.4,.6,1],material:'illustrative_solid'}};
it('renders parent hierarchy, immediate rotate controls and measured native poses',()=>{
 const child={...object,id:'child',parent:'beam',position_m:[.2,0,0]},world:World={schema_version:1,id:'world',revision:0,units:'SI',objects:[object,child],environment:{gravity_m_s2:[0,0,-9.81],timestep_s:.005,duration_s:1},unsupported:[]};
 const props={world,selection:'beam',onSelect:vi.fn(),onTransform:vi.fn(),snap:true,collision:false};
 const view=render(<WorldViewport {...props} mode="translate"/>);let scene=draw.mock.calls.at(-1)![0];expect(scene.getObjectByName('child').parent.name).toBe('beam');
 view.rerender(<WorldViewport {...props} mode="rotate"/>);scene=draw.mock.calls.at(-1)![0];expect(scene.children.find((c:any)=>c.isTransformControlsRoot).children.find((c:any)=>c.isTransformControlsGizmo).mode).toBe('rotate');
 view.rerender(<WorldViewport {...props} mode="rotate" sample={{time_s:1,qpos:[.5],qvel:[0],contacts:0,actuator_force:[],poses:[{id:'beam',position_m:[.3,.1,.2],quaternion_wxyz:[1,0,0,0]},{id:'child',position_m:[.4,.2,.2],quaternion_wxyz:[1,0,0,0]}]}}/>);
 scene=draw.mock.calls.at(-1)![0];expect(scene.getObjectByName('child').position.toArray()).toEqual([.4,.2,.2]);expect(scene.getObjectByName('child').parent).toBe(scene);view.unmount();
});
it('uses full SI extents and Z-axis circular geometry',()=>{
 const geometry=worldGeometry({...object,geometry:'cylinder',dimensions_m:[.1,.1,.4]});geometry.computeBoundingBox();const b=geometry.boundingBox!;expect(b.max.z-b.min.z).toBeCloseTo(.4);expect(b.max.x-b.min.x).toBeCloseTo(.1);geometry.dispose();
});

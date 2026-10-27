import {render} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import raw from '../test/mobility_rover.json?raw';
import WorldViewport from './WorldViewport';
const {draw}=vi.hoisted(()=>({draw:vi.fn()}));
vi.mock('three',async original=>{const actual=await original<typeof import('three')>();return {...actual,WebGLRenderer:class{domElement=document.createElement('canvas');setClearColor(){}setPixelRatio(){}setSize(){}dispose(){}render=draw;}};});
it('wheel intermediaries retain their real tiny primitives rather than inferred arm housings',()=>{
 const b=JSON.parse(raw);const view=render(<WorldViewport world={b.project.world} shapeParts={b.shapebase.parts} selection="front_left_wheel" onSelect={vi.fn()} onTransform={vi.fn()} mode="translate" snap={false} collision={false} readOnly/>);
 const scene=draw.mock.calls.at(-1)![0],joint=scene.getObjectByName('front_left_wheel_joint');
 const mesh=joint.children.find((c:any)=>c.isMesh);expect(mesh).toBeDefined();expect(mesh.geometry.parameters.width).toBeCloseTo(.005);expect(joint.children.some((c:any)=>c.userData?.mechanicalSpec)).toBe(false);
 expect(scene.getObjectByName('shape:shape_front_left_wheel')).toBeDefined();expect(scene.getObjectByName('shape:shape_chassis')).toBeDefined();view.unmount();
});

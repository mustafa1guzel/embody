import {render} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import raw from '../test/shapebase.json?raw';
import WorldViewport from './WorldViewport';
const {draw}=vi.hoisted(()=>({draw:vi.fn()}));
vi.mock('three',async original=>{const actual=await original<typeof import('three')>();return {...actual,WebGLRenderer:class{domElement=document.createElement('canvas');setClearColor(){}setPixelRatio(){}setSize(){}dispose(){}render=draw;}};});
it('governs parametric bodies in the actual world view and isolates meshes without changing body frames',()=>{
 const b=JSON.parse(raw),change=vi.fn(),props={world:b.project.world,shapeParts:b.shapebase.parts,selection:'link_one',onSelect:vi.fn(),onTransform:change,mode:'translate' as const,snap:true,collision:false};
 const view=render(<WorldViewport {...props}/>);let scene=draw.mock.calls.at(-1)![0];
 const controls=()=>scene.children.find((c:any)=>c.isTransformControlsRoot);
 expect(controls().visible).toBe(false);const root=scene.getObjectByName('link_one');expect(root.parent.name).toBe('shoulder');const position=root.position.toArray();
 view.rerender(<WorldViewport {...props} isolatedBody="link_one"/>);scene=draw.mock.calls.at(-1)![0];expect(root.position.toArray()).toEqual(position);expect(root.parent.name).toBe('shoulder');expect(scene.getObjectByName('shape:shape_link_one').visible).toBe(true);expect(scene.getObjectByName('shape:shape_link_two').visible).toBe(false);
 view.rerender(<WorldViewport {...props} selection="shoulder"/>);scene=draw.mock.calls.at(-1)![0];expect(controls().visible).toBe(true);expect(change).not.toHaveBeenCalled();view.unmount();
});

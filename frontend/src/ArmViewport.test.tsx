import raw from '../test/arm_evidence.json?raw';
import {createRef} from 'react';
import {render} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import * as THREE from 'three';
import Viewport,{geometryFor,measuredPosition,measuredQuaternion} from './Viewport';
const evidence=JSON.parse(raw).experiments.arm_nominal;
const spy=vi.fn();
vi.mock('three',async original=>{const real=await original<typeof import('three')>();class Renderer{domElement=document.createElement('canvas');setPixelRatio(){}setClearColor(){}setSize(){}render=spy;dispose(){}forceContextLoss(){}}return {...real,WebGLRenderer:Renderer};});
it('applies measured articulated position AND rotation to actual Three meshes, with mocked GPU',()=>{
 const scene=evidence.scene,samples=evidence.variants.attempt_1.samples;
 const props={scene,sample:samples[0],selection:'geom:2',onSelect:vi.fn(),visible:true,cameraMemory:createRef<any>()};
 const v=render(<Viewport {...props}/>);v.rerender(<Viewport {...props} sample={samples[600]}/>);
 const world=spy.mock.calls.at(-1)![0];
 for(const g of scene.geoms){const mesh=world.getObjectByName(g.id);expect(mesh.position.toArray()).toEqual(measuredPosition(g,scene,samples[600]));const [w,x,y,z]=measuredQuaternion(g,scene,samples[600]);expect(mesh.quaternion.toArray()).toEqual([x,y,z,w]);}
 expect(geometryFor(scene.geoms.find((g:any)=>g.name==='tool_marker'))).toBeInstanceOf(THREE.SphereGeometry);
 expect(()=>measuredPosition(scene.geoms[0],scene,{...samples[0],geom_poses:[]})).toThrow('unavailable');
 v.unmount();
});

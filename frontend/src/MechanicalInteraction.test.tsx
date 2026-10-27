import {render,screen,fireEvent} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import * as THREE from 'three';
import WorldViewport from './WorldViewport';
import type {World,WorldObject} from './engineeringTypes';
const {draw}=vi.hoisted(()=>({draw:vi.fn()}));
vi.mock('three',async original=>{const actual=await original<typeof import('three')>();return {...actual,WebGLRenderer:class{domElement=document.createElement('canvas');setClearColor(){}setPixelRatio(){}setSize(){}dispose(){}render=draw;}};});
const o:WorldObject={id:'drive',name:'Driven hinge',parent:null,kind:'dynamic',geometry:'box',position_m:[0,0,.2],rotation_rad:[.1,.2,.3],dimensions_m:[.04,.04,.04],mass_kg:.2,joint:{kind:'revolute',axis:[0,1,0],range:[0,1],initial_position:.2,initial_velocity:0,damping:.01},actuator:{limit:.12,command:0,unit:'N*m'},contact:{enabled:true,friction:[.7,.005,.0001]},visual:{rgba:[.3,.4,.6,1],material:'illustrative_solid'}};
const world:World={schema_version:1,id:'w',revision:0,units:'SI',objects:[o],environment:{gravity_m_s2:[0,0,-9.81],duration_s:1,timestep_s:.005},unsupported:[]};
function controls(scene:THREE.Scene){return scene.children.find((c:any)=>c.isTransformControlsRoot) as any;}
it('read-only previews cannot attach a gizmo or dispatch transforms and expose authoritative inspection',()=>{
 const changed=vi.fn(),selected=vi.fn(),raw=JSON.stringify(world);
 const view=render(<WorldViewport world={world} selection="drive" onSelect={selected} onTransform={changed} mode="translate" snap collision={false} readOnly/>);
 let scene=draw.mock.calls.at(-1)![0];expect(controls(scene).visible).toBe(false);expect(scene.getObjectByName('drive').getObjectByName('shaft')).toBeTruthy();
 expect(screen.getByTestId('mechanical-inspection')).toHaveTextContent('0.04 × 0.04 × 0.04 m');expect(screen.getByTestId('mechanical-inspection')).toHaveTextContent('revolute · axis [0, 1, 0]');
 fireEvent.click(screen.getByRole('button',{name:'Native collision geometry'}));scene=draw.mock.calls.at(-1)![0];expect(scene.getObjectByName('shaft')).toBeUndefined();expect(scene.getObjectByName('drive').children[0].material.wireframe).toBe(true);
 expect(changed).not.toHaveBeenCalled();expect(JSON.stringify(world)).toBe(raw);view.unmount();
});
it('preserves authoring transforms, uses exact measured quaternions and reuses meshes during playback',()=>{
 const props={world,selection:'drive',onSelect:vi.fn(),onTransform:vi.fn(),mode:'rotate' as const,snap:true,collision:false};
 const v=render(<WorldViewport {...props}/>);let scene=draw.mock.calls.at(-1)![0];expect(controls(scene).visible).toBe(true);const root=scene.getObjectByName('drive'),shaft=root.getObjectByName('shaft');
 const expected=new THREE.Quaternion().setFromEuler(new THREE.Euler(...o.rotation_rad as [number,number,number])).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),.2));expect(root.quaternion.angleTo(expected)).toBeLessThan(1e-7);
 const sample={time_s:1,qpos:[.4],qvel:[0],contacts:0,actuator_force:[0],poses:[{id:'drive',position_m:[.1,.2,.3],quaternion_wxyz:[Math.SQRT1_2,0,0,Math.SQRT1_2]}]};
 v.rerender(<WorldViewport {...props} sample={sample}/>);scene=draw.mock.calls.at(-1)![0];expect(scene.getObjectByName('drive')).toBe(root);expect(root.getObjectByName('shaft')).toBe(shaft);expect(root.position.toArray()).toEqual([.1,.2,.3]);expect(root.quaternion.toArray()).toEqual([0,0,Math.SQRT1_2,Math.SQRT1_2]);expect(controls(scene).visible).toBe(false);v.unmount();
});
it('raycasts the display housing to the original body and inspects without making an edit',()=>{
 vi.stubGlobal('PointerEvent',MouseEvent);const onSelect=vi.fn(),onTransform=vi.fn();
 const view=render(<WorldViewport world={world} selection="" onSelect={onSelect} onTransform={onTransform} mode="translate" snap collision={false} readOnly/>);
 const [scene,camera]=draw.mock.calls.at(-1)!,canvas=view.container.querySelector('canvas')!;canvas.getBoundingClientRect=()=>new DOMRect(0,0,800,600);canvas.setPointerCapture=vi.fn();canvas.releasePointerCapture=vi.fn();scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
 const p=scene.getObjectByName('drive').getWorldPosition(new THREE.Vector3()).project(camera),coordinates={clientX:(p.x+1)*400,clientY:(1-p.y)*300};
 fireEvent.pointerDown(canvas,coordinates);fireEvent.pointerUp(canvas,coordinates);expect(onSelect).toHaveBeenCalledWith('drive');expect(screen.getByTestId('mechanical-inspection')).toHaveTextContent('Driven hinge');expect(onTransform).not.toHaveBeenCalled();view.unmount();
});

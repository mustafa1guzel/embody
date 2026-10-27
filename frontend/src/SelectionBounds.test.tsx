import {render,screen,fireEvent} from '@testing-library/react';import {expect,it,vi} from 'vitest';import * as THREE from 'three';
import WorldViewport from './WorldViewport';import type {World,WorldObject} from './engineeringTypes';
const {draw}=vi.hoisted(()=>({draw:vi.fn()}));vi.mock('three',async original=>({...await original<typeof import('three')>(),WebGLRenderer:class{domElement=document.createElement('canvas');setClearColor(){}setPixelRatio(){}setSize(){}dispose(){}render=draw;}}));
const base:WorldObject={id:'parent',name:'Parent',parent:null,kind:'static',geometry:'box',position_m:[0,0,.1],rotation_rad:[0,0,0],dimensions_m:[.1,.1,.1],mass_kg:0,joint:null,actuator:null,contact:{enabled:true,friction:[.7,.005,.0001]},visual:{rgba:[.4,.5,.6,1],material:'illustrative_solid'}};
const world:World={schema_version:1,id:'selection_fixture',revision:0,units:'SI',objects:[base,{...base,id:'child',name:'Child',parent:'parent',position_m:[10,0,0]}],environment:{gravity_m_s2:[0,0,-9.81],duration_s:1,timestep_s:.005},unsupported:[]};
it('highlights and fits only the selected body geometry, excluding registered child-body geometry',()=>{
 const view=render(<WorldViewport world={world} selection="parent" onSelect={vi.fn()} onTransform={vi.fn()} mode="translate" snap={false} collision={false} readOnly controlledSelection/>);
 const scene=draw.mock.calls.at(-1)![0] as THREE.Scene;const outline=scene.children.find(o=>o instanceof THREE.Box3Helper) as THREE.Box3Helper;expect(outline.box.max.x).toBeLessThan(1);expect(outline.visible).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Fit selected part'}));const camera=draw.mock.calls.at(-1)![1] as THREE.PerspectiveCamera;expect(camera.position.x).toBeLessThan(2);
 view.rerender(<WorldViewport world={world} selection="" onSelect={vi.fn()} onTransform={vi.fn()} mode="translate" snap={false} collision={false} readOnly controlledSelection/>);expect(outline.visible).toBe(false);view.unmount();
});

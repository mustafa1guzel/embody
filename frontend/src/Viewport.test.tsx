import evidenceRaw from '../test/recorded-study.public.json?raw';
import {createRef} from 'react';
import {fireEvent,render,screen} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import * as THREE from 'three';
import Viewport,{geometryFor,measuredPosition} from './Viewport';
import type {Experiment,SceneObject} from './types';
const fixture=JSON.parse(evidenceRaw);
const experiment:Experiment=fixture.experiments.A;
const renderSpy=vi.fn(),disposeSpy=vi.fn();
vi.mock('three',async importOriginal=>{
 const real=await importOriginal<typeof import('three')>();
 // GPU transport only is mocked: real Three meshes, transforms, cameras and
 // OrbitControls are used. This does not constitute browser/WebGL visual QA.
 class TestRenderer{domElement=document.createElement('canvas');setPixelRatio(){}setClearColor(){}setSize(){}render=renderSpy;dispose=disposeSpy;forceContextLoss(){}}
 return {...real,WebGLRenderer:TestRenderer};
});
describe('recorded MuJoCo geometry, actual Three objects; mocked GPU transport',()=>{
 it('uses real box, capsule and plane dimensions and rejects unknown types',()=>{
  const box=geometryFor(experiment.scene.geoms.find(g=>g.name==='carriage_box')!);box.computeBoundingBox();
  const size=box.boundingBox!.getSize(new THREE.Vector3());expect(size.x).toBeCloseTo(.26);expect(size.y).toBeCloseTo(.32);expect(size.z).toBeCloseTo(.16);box.dispose();
  const capsule=geometryFor(experiment.scene.geoms.find(g=>g.name==='rail_track')!);capsule.computeBoundingBox();
  expect(capsule.boundingBox!.getSize(new THREE.Vector3()).z).toBeCloseTo(3.66);capsule.dispose();
  expect(()=>geometryFor({id:'test',name:'test',kind:'geom',size:[1,1,1],type:99} as SceneObject)).toThrow('Unsupported');
 });
 it('maps every recorded pose without interpolation or changing static geometry',()=>{
  for(const variant of Object.values(experiment.variants))for(const s of variant.samples){
   const bumper=experiment.scene.geoms.find(g=>g.name==='front_bumper')!,wall=experiment.scene.geoms.find(g=>g.name==='wall')!;
   expect(measuredPosition(bumper,experiment.scene,s)[0]+bumper.size[0]).toBeCloseTo(Number(s.bumper_front_x),12);
   expect(measuredPosition(wall,experiment.scene,s)).toEqual(wall.position);
  }
 });
 it('updates actual mesh positions, selection materials, projection, grid and cleanup',()=>{
  const camera=createRef<any>();const onSelect=vi.fn();const samples=experiment.variants.original.samples;
  const props={scene:experiment.scene,sample:samples[0],selection:'geom:3',onSelect,visible:true,cameraMemory:camera};
  const view=render(<Viewport {...props}/>);
  let [world,cam]=renderSpy.mock.calls.at(-1)!;
  expect(cam).toBeInstanceOf(THREE.PerspectiveCamera);
  expect(world.getObjectByName('geom:3').material.emissive.getHex()).not.toBe(0);
  view.rerender(<Viewport {...props} sample={samples[400]} selection="geom:5"/>);
  [world]=renderSpy.mock.calls.at(-1)!;
  expect(world.getObjectByName('geom:3').position.x).toBeCloseTo(samples[400].position,12);
  expect(world.getObjectByName('geom:5').material.emissive.getHex()).not.toBe(0);
  fireEvent.click(screen.getByRole('button',{name:'Toggle projection'}));
  expect(renderSpy.mock.calls.at(-1)![1]).toBeInstanceOf(THREE.OrthographicCamera);
  fireEvent.click(screen.getByRole('button',{name:'Grid'}));expect(screen.getByRole('button',{name:'Grid'})).toHaveAttribute('aria-pressed','false');
  fireEvent.click(screen.getByRole('button',{name:'Axes'}));expect(screen.getByRole('button',{name:'Axes'})).toHaveAttribute('aria-pressed','false');
  fireEvent.click(screen.getByRole('button',{name:'Fit scene'}));fireEvent.click(screen.getByRole('button',{name:'Reset camera'}));
  view.unmount();expect(disposeSpy).toHaveBeenCalled();expect(document.querySelector('canvas')).toBeNull();
 });
});

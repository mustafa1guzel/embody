import {expect,it} from 'vitest';
import * as THREE from 'three';
import {MechanicalLibrary,roundedPlate,worldMechanicalSpec,recordedMechanicalSpec,validateMechanicalSpec,type MechanicalSpec} from './mechanicalVisuals';
import type {World,WorldObject} from './engineeringTypes';
import armRaw from '../test/arm_evidence.json?raw';
const identity={body:'body:2',joint:'joint:0',link:'body:2',actuator:'actuator:0'};
it('generates rounded through-holes at parameterized attachment centres with finite geometry',()=>{
 const library=new MechanicalLibrary();
 for(const length of [.15,.45,.6]){
  const g=library.create({kind:'link',dimensions:[length,.04,.02],identity,endpointSpan:true});g.updateMatrixWorld(true);
  expect(g.userData.attachmentCenters).toEqual([[-length/2,0,0],[length/2,0,0]]);
  const plate=g.getObjectByName('rounded-link-with-through-holes') as THREE.Mesh;
  plate.geometry.computeBoundingBox();expect(plate.geometry.boundingBox!.getSize(new THREE.Vector3()).x).toBeCloseTo(length+.04,2);
  const ray=new THREE.Raycaster(new THREE.Vector3(length/2,0,.1),new THREE.Vector3(0,0,-1));expect(ray.intersectObject(plate)).toHaveLength(0);
  g.traverse(o=>{if(o instanceof THREE.Mesh){expect([...o.geometry.attributes.position.array].every(Number.isFinite)).toBe(true);expect(o.userData.semantic).toEqual(identity);}});
 }
 library.dispose();
});
it('aligns shafts with the actual axis, preserves all semantic identifiers and shares bounded resources',()=>{
 const l=new MechanicalLibrary(),s:MechanicalSpec={kind:'actuator',dimensions:[.005,.005,.005],housingDiameter:.034,axis:[0,-1,0],identity:{body:'hinge',joint:'joint_hinge',actuator:'motor_hinge',mount:'support',sensor:'range',component:'servo'}};
 const a=l.create(s),b=l.create(s);a.updateMatrixWorld(true);const module=a.getObjectByName('axis-aligned-joint-module')!;
 expect(new THREE.Vector3(0,0,1).applyQuaternion(module.quaternion).distanceTo(new THREE.Vector3(0,-1,0))).toBeLessThan(1e-12);
 const shaft=a.getObjectByName('shaft') as THREE.Mesh;expect(shaft.geometry).toBe((b.getObjectByName('shaft') as THREE.Mesh).geometry);
 expect(a.userData.semantic).toEqual(s.identity);expect(a.userData.mechanicalSpec.dimensions).toEqual([.005,.005,.005]);expect(l.cacheSize).toBeLessThan(20);l.dispose();
});
it('all supported families render finite meshes and invalid dimensions/axes fail explicitly',()=>{
 const l=new MechanicalLibrary();for(const kind of ['link','joint','actuator','support','plate','sensor_mount'] as const){const g=l.create({kind,dimensions:[.1,.05,.04],identity});let meshes=0;g.traverse(o=>{if(o instanceof THREE.Mesh){meshes++;expect([...o.geometry.attributes.position.array].every(Number.isFinite)).toBe(true);}});expect(meshes).toBeGreaterThan(0);}
 expect(()=>validateMechanicalSpec({kind:'link',dimensions:[NaN,1,1],identity})).toThrow('finite');expect(()=>validateMechanicalSpec({kind:'joint',dimensions:[1,1,1],axis:[1,1,0],identity})).toThrow('unit');expect(()=>roundedPlate(.2,.05,.01,[{x:.2,y:0,r:.01}])).toThrow('outside');l.dispose();
});
it('uses actual world roles and joint fields; unknown primitives remain authoritative fallback',()=>{
 const o:WorldObject={id:'pivot',name:'Any name',parent:'support',kind:'dynamic',geometry:'box',position_m:[0,0,.1],rotation_rad:[0,0,0],dimensions_m:[.005,.005,.005],mass_kg:.001,joint:{kind:'revolute',axis:[0,-1,0],range:[0,1.65],initial_position:0,initial_velocity:0,damping:.015},actuator:{limit:.12,command:0,unit:'N*m'},contact:{enabled:true,friction:[.7,.005,.0001]},visual:{rgba:[.3,.4,.5,1],material:'illustrative_solid'}};
 const w={objects:[o]} as World,before=JSON.stringify(w),s=worldMechanicalSpec(o,w)!;expect(s.identity).toEqual({body:'pivot',geom:'geom_pivot',joint:'joint_pivot',actuator:'motor_pivot'});expect(s.axis).toEqual([0,-1,0]);expect(s.dimensions).toEqual(o.dimensions_m);
 expect(worldMechanicalSpec({...o,id:'m',joint:null,actuator:null,kind:'anchor'},w,{world_roles:{sensor:'m'},component_roles:{sensor:'actual_sensor'}})?.identity.component).toBe('actual_sensor');
 expect(worldMechanicalSpec({...o,joint:null,actuator:null,kind:'obstacle'},w)).toBeNull();expect(JSON.stringify(w)).toBe(before);
 expect(worldMechanicalSpec(o,w,{world_roles:{pivot:'pivot'},component_roles:{servo:'actual_servo'}})?.identity).toEqual({body:'pivot',geom:'geom_pivot',joint:'joint_pivot',actuator:'motor_pivot',mount:'support',component:'actual_servo'});
});
it('maps measured arm geoms to their actual bodies, joint identities and native full dimensions',()=>{
 const scene=JSON.parse(armRaw).experiments.arm_nominal.scene;
 const s=recordedMechanicalSpec(scene.geoms.find((g:any)=>g.name==='link2_box'),scene)!;expect(s.dimensions).toEqual([.45,.04,.035]);expect(s.identity).toEqual({body:'body:3',geom:'geom:5',joint:'joint:1',actuator:'actuator:1',link:'body:3'});
 expect(recordedMechanicalSpec(scene.geoms.find((g:any)=>g.name==='tool_marker'),scene)).toBeNull();
});

import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {MechanicalLibrary,recordedMechanicalSpec,disposeUnshared,MECHANICAL_ACCURACY} from './mechanicalVisuals';
import {geometryFor} from './Viewport';
import type {DeviceRun,DeviceSample} from './hardwareTypes';
export function applyDevicePoses(meshes:THREE.Object3D[],sample:DeviceSample){meshes.forEach((m,i)=>{const p=sample.geom_poses[i];if(!p)throw new Error('Measured device pose missing');m.position.fromArray(p.position);const [w,x,y,z]=p.quaternion_wxyz;m.quaternion.set(x,y,z,w);});}
export default function DeviceViewport({run,sample}:{run:DeviceRun;sample:DeviceSample}){
 const host=useRef<HTMLDivElement>(null),engine=useRef<{meshes:THREE.Object3D[];render:()=>void}|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  if(!host.current||!run.scene)return;const container=host.current;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setError('WebGL unavailable; measured device telemetry remains accessible.');return;}
  renderer.setClearColor(document.documentElement.dataset.theme==='dark'?'#191e23':'#eeefeb');renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.appendChild(renderer.domElement);const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,.01,20);camera.up.set(0,0,1);camera.position.set(.7,-1,.75);
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(.3,-.03,.15);controls.update();scene.add(new THREE.HemisphereLight(0xffffff,0x445566,2));
  const library=new MechanicalLibrary();
  const meshes=run.scene.geoms.map(g=>{const spec=recordedMechanicalSpec({...g,kind:'geom'});const mesh=spec?library.create(spec):new THREE.Mesh(geometryFor({...g,kind:'geom'}),new THREE.MeshStandardMaterial({color:g.type===0?'#dfe4e2':new THREE.Color(...g.rgba.slice(0,3) as [number,number,number]),side:THREE.DoubleSide}));if(spec?.kind==='link'){const drive=library.create({kind:'actuator',dimensions:[spec.dimensions[1],spec.dimensions[1],spec.dimensions[2]],identity:spec.identity,axis:[0,-1,0]});drive.position.x=-g.size[0];mesh.add(drive);}mesh.name=g.id;scene.add(mesh);return mesh;});
  applyDevicePoses(meshes,sample);const render=()=>renderer.render(scene,camera);engine.current={meshes,render};controls.addEventListener('change',render);
  const resize=()=>{camera.aspect=Math.max(1,container.clientWidth)/Math.max(1,container.clientHeight);camera.updateProjectionMatrix();renderer.setSize(Math.max(1,container.clientWidth),Math.max(1,container.clientHeight));render();};const observer=new ResizeObserver(resize);observer.observe(container);resize();
  return()=>{engine.current=null;observer.disconnect();controls.dispose();meshes.forEach(disposeUnshared);library.dispose();renderer.dispose();renderer.domElement.remove();};
 },[run]);
 useEffect(()=>{if(engine.current){applyDevicePoses(engine.current.meshes,sample);engine.current.render();}},[sample]);
 return <div ref={host} className="device-canvas" title={MECHANICAL_ACCURACY}>{error&&<p role="alert">{error}</p>}</div>;
}

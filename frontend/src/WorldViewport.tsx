import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {TransformControls} from 'three/examples/jsm/controls/TransformControls.js';
import {shapeModel,type ShapePart} from './shapeGeometry';
import type {World,WorldObject,WorldSample} from './engineeringTypes';
import {MechanicalLibrary,worldMechanicalSpec,disposeUnshared,MECHANICAL_ACCURACY,type MechanicalContext} from './mechanicalVisuals';

export function worldGeometry(o:WorldObject):THREE.BufferGeometry{
 const [x,y,z]=o.dimensions_m;
 if(o.geometry==='sphere')return new THREE.SphereGeometry(x/2,24,16);
 if(o.geometry==='plane')return new THREE.PlaneGeometry(x,y);
 if(o.geometry==='cylinder')return new THREE.CylinderGeometry(x/2,x/2,z,24).rotateX(Math.PI/2);
 if(o.geometry==='capsule')return new THREE.CapsuleGeometry(x/2,z-x,8,16).rotateX(Math.PI/2);
 return new THREE.BoxGeometry(x,y,z);
}
/** Same parent-local authoring / absolute native-pose contract for every display. */
export function applyWorldTransforms(groups:Map<string,THREE.Group>,world:World,scene:THREE.Scene,sample?:WorldSample){
 for(const o of world.objects){
  const root=groups.get(o.id)!;
  if(sample){const p=sample.poses.find(p=>p.id===o.id);if(!p)throw new Error('Measured body pose missing: '+o.id);root.position.fromArray(p.position_m);const [w,x,y,z]=p.quaternion_wxyz;root.quaternion.set(x,y,z,w);scene.add(root);}
  else{root.position.fromArray(o.position_m);root.rotation.set(...o.rotation_rad as [number,number,number],'XYZ');if(o.joint){const axis=new THREE.Vector3(...o.joint.axis),q=o.joint.initial_position;if(o.joint.kind==='revolute')root.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(axis,q));if(o.joint.kind==='prismatic')root.position.add(axis.multiplyScalar(q).applyQuaternion(root.quaternion));}(o.parent?groups.get(o.parent)!:scene).add(root);}
 }
 scene.updateMatrixWorld(true);
}
export default function WorldViewport({world,selection,onSelect,onTransform,mode,snap,collision,sample,readOnly=false,controlledSelection=false,visualContext,shapeParts,isolatedBody,fitToken}:{world:World;selection:string;onSelect:(id:string)=>void;onTransform:(id:string,p:number[],r:number[])=>void;mode:'translate'|'rotate';snap:boolean;collision:boolean;sample?:WorldSample;readOnly?:boolean;controlledSelection?:boolean;visualContext?:MechanicalContext;shapeParts?:ShapePart[];isolatedBody?:string;fitToken?:number}){
 const host=useRef<HTMLDivElement>(null),engine=useRef<any>(null),[error,setError]=useState(''),[inspected,setInspected]=useState(''),[native,setNative]=useState(collision);
 const selected=controlledSelection?selection:selection||inspected;
 const refs=useRef({world,selection:selected,onSelect,onTransform,collision:native,sample,readOnly,visualContext,shapeParts,isolatedBody});refs.current={world,selection:selected,onSelect,onTransform,collision:native,sample,readOnly,visualContext,shapeParts,isolatedBody};
 const memory=useRef({position:[1.1,-1.6,1.2],target:[.2,0,.2]});
 useEffect(()=>setNative(collision),[collision]);
 useEffect(()=>{
  if(!host.current)return;const container=host.current;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setError('WebGL unavailable; world visual QA UNVERIFIED.');return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.appendChild(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(45,1,.005,4000);camera.up.set(0,0,1);camera.position.fromArray(memory.current.position);
  const orbit=new OrbitControls(camera,renderer.domElement);orbit.target.fromArray(memory.current.target);orbit.update();
  scene.add(new THREE.HemisphereLight(0xffffff,0x84959c,2.3));const light=new THREE.DirectionalLight(0xffffff,2.6);light.position.set(1,-2,4);scene.add(light);
  const grid=new THREE.GridHelper(4,40,0xaab8b6,0xd6ded9);grid.rotateX(Math.PI/2);grid.position.z=-.0005;scene.add(grid);
  const gizmo=new TransformControls(camera,renderer.domElement);gizmo.setSize(.8);scene.add(gizmo.getHelper());
  const library=new MechanicalLibrary(),bounds=new THREE.Box3(),outline=new THREE.Box3Helper(bounds,0x397d90);outline.visible=false;scene.add(outline);
  let groups=new Map<string,THREE.Group>(),builtWorld:World|null=null,builtCollision:boolean|undefined,builtContext:MechanicalContext|undefined,builtShapes:ShapePart[]|undefined;
  const render=()=>{bounds.makeEmpty();const chosen=groups.get(refs.current.selection);if(chosen){scene.updateMatrixWorld(true);for(const child of chosen.children)if(!groups.has(child.name)&&child.visible)bounds.expandByObject(child);}outline.visible=!bounds.isEmpty();renderer.render(scene,camera);if(renderer.info){renderer.domElement.dataset.renderCalls=String(renderer.info.render.calls);renderer.domElement.dataset.triangles=String(renderer.info.render.triangles);renderer.domElement.dataset.geometries=String(renderer.info.memory.geometries);}};
  const clear=()=>{gizmo.detach();for(const root of groups.values()){root.removeFromParent();disposeUnshared(root);}groups.clear();};
  const themeChange=()=>{renderer.setClearColor(document.documentElement.dataset.theme==='dark'?'#191e23':'#eeefeb');render();};
  function update(){
   const r=refs.current;
   if(builtWorld!==r.world||builtCollision!==r.collision||builtContext!==r.visualContext||builtShapes!==r.shapeParts){
    clear();builtWorld=r.world;builtCollision=r.collision;builtContext=r.visualContext;builtShapes=r.shapeParts;
    for(const o of r.world.objects){
     const root=new THREE.Group();root.name=o.id;root.userData.objectId=o.id;
     // A wheel child is not an arm link: do not infer an oversized arm
     // housing from its diameter. Keep the explicit small joint proxy visible.
     const wheelJoint=r.shapeParts?.some(p=>p.spec.family==='wheel'&&p.spec.parent_body_id===o.id);
     const spec=wheelJoint?null:worldMechanicalSpec(o,r.world,r.visualContext);
     const part=r.shapeParts?.find(p=>p.spec.body_id===o.id);
     if(!r.collision&&part)root.add(shapeModel(part));
     else if(!r.collision&&spec)root.add(library.create(spec));
     else{const mesh=new THREE.Mesh(worldGeometry(o),new THREE.MeshStandardMaterial({color:o.geometry==='plane'?'#dfe4e2':new THREE.Color(...o.visual.rgba.slice(0,3) as [number,number,number]),roughness:.7,side:THREE.DoubleSide,wireframe:r.collision}));mesh.visible=!r.collision||o.contact.enabled;mesh.userData.objectId=o.id;root.add(mesh);}
     if(o.joint&&o.joint.kind!=='free'){const length=Math.max(.02,Math.min(.10,Math.max(...o.dimensions_m)*1.3));root.add(new THREE.ArrowHelper(new THREE.Vector3(...o.joint.axis),new THREE.Vector3(),length,0x397d90,length*.22,length*.12));}
     for(const child of root.children)child.userData.baselineVisible=child.visible;
     groups.set(o.id,root);
    }
   }
   applyWorldTransforms(groups,r.world,scene,r.sample);
   for(const [id,root] of groups)for(const child of root.children)if(!groups.has(child.name))child.visible=child.userData.baselineVisible!==false&&(!r.isolatedBody||r.isolatedBody===id);
   gizmo.detach();if(!r.sample&&!r.readOnly&&!r.shapeParts?.some(p=>p.spec.body_id===r.selection)&&groups.has(r.selection))gizmo.attach(groups.get(r.selection)!);render();
  }
  gizmo.addEventListener('dragging-changed',e=>{orbit.enabled=!e.value;});gizmo.addEventListener('change',render);
  gizmo.addEventListener('mouseUp',()=>{
   if(refs.current.readOnly||refs.current.sample||refs.current.shapeParts?.some(p=>p.spec.body_id===gizmo.object?.name))return;const o=gizmo.object;if(!o)return;
   const spec=refs.current.world.objects.find(x=>x.id===o.name)!,position=o.position.clone(),rotation=o.quaternion.clone(),j=spec.joint;
   if(j){const axis=new THREE.Vector3(...j.axis);if(j.kind==='revolute')rotation.multiply(new THREE.Quaternion().setFromAxisAngle(axis,-j.initial_position));if(j.kind==='prismatic')position.sub(axis.multiplyScalar(j.initial_position).applyQuaternion(rotation));}
   const euler=new THREE.Euler().setFromQuaternion(rotation,'XYZ');refs.current.onTransform(o.name,position.toArray(),[euler.x,euler.y,euler.z]);
  });
  let down=[0,0];const pointerDown=(e:PointerEvent)=>{down=[e.clientX,e.clientY];};
  const select=(e:PointerEvent)=>{if(gizmo.axis||Math.hypot(e.clientX-down[0],e.clientY-down[1])>4)return;const r=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(2*(e.clientX-r.left)/r.width-1,1-2*(e.clientY-r.top)/r.height),camera);const hit=ray.intersectObjects([...groups.values()],true).find(h=>h.object.userData.objectId&&(!refs.current.isolatedBody||h.object.userData.objectId===refs.current.isolatedBody)&&refs.current.world.objects.find(o=>o.id===h.object.userData.objectId)?.geometry!=='plane');if(hit){const id=hit.object.userData.objectId;setInspected(id);refs.current.onSelect(id);}};
  renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointerup',select);orbit.addEventListener('change',render);window.addEventListener('embody-theme-change',themeChange);
  const resize=()=>{const width=Math.max(1,container.clientWidth),height=Math.max(1,container.clientHeight);camera.aspect=width/height;camera.updateProjectionMatrix();renderer.setSize(width,height);render();};const observer=new ResizeObserver(resize);observer.observe(container);
  const fit=(selectedOnly=false,mechanismOnly=false)=>{const b=new THREE.Box3();for(const [id,root] of groups)if(refs.current.world.objects.find(o=>o.id===id)?.geometry!=='plane'&&(!selectedOnly||id===refs.current.selection)&&(!mechanismOnly||id!==refs.current.visualContext?.world_roles.target)){if(refs.current.isolatedBody||selectedOnly){if(!refs.current.isolatedBody||id===refs.current.isolatedBody)for(const child of root.children)if(!groups.has(child.name)&&child.visible)b.expandByObject(child);}else b.expandByObject(root);}if(b.isEmpty()){orbit.target.set(0,0,.1);camera.position.set(1.1,-1.6,1.2);}else{const center=b.getCenter(new THREE.Vector3()),size=b.getSize(new THREE.Vector3());const direction=new THREE.Vector3(.6,-.8,.65).normalize();let distance=Math.max(.25,size.length()*1.5)/Math.min(camera.aspect,1);
   if(refs.current.isolatedBody){const right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,0,1),direction).normalize(),up=new THREE.Vector3().crossVectors(direction,right).normalize(),tangent=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));distance=.04;for(const x of [b.min.x,b.max.x])for(const y of [b.min.y,b.max.y])for(const z of [b.min.z,b.max.z]){const v=new THREE.Vector3(x,y,z).sub(center),depth=v.dot(direction);distance=Math.max(distance,Math.abs(v.dot(right))/(tangent*camera.aspect)+depth,Math.abs(v.dot(up))/tangent+depth);}distance*=1.15;}
   camera.position.copy(center).addScaledVector(direction,distance);orbit.target.copy(center);}orbit.update();render();};
  engine.current={update,gizmo,fit,reset:()=>{camera.position.set(1.1,-1.6,1.2);orbit.target.set(.2,0,.2);orbit.update();render();}};update();resize();themeChange();
  return()=>{memory.current={position:camera.position.toArray(),target:orbit.target.toArray()};engine.current=null;observer.disconnect();window.removeEventListener('embody-theme-change',themeChange);renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointerup',select);clear();disposeUnshared(outline);disposeUnshared(grid);library.dispose();gizmo.dispose();orbit.dispose();renderer.dispose();renderer.domElement.remove();};
 },[]);
 useEffect(()=>{engine.current?.update();},[world,selected,native,sample,readOnly,visualContext,shapeParts,isolatedBody]);
 useEffect(()=>{engine.current?.fit();},[world.id]);
 useEffect(()=>{if(fitToken!==undefined)engine.current?.fit();},[fitToken]);
 useEffect(()=>{const g=engine.current?.gizmo;if(g){g.setMode(mode);g.setTranslationSnap(snap ? .01 : null);g.setRotationSnap(snap?Math.PI/12:null);}},[mode,snap]);
 useEffect(()=>{if(isolatedBody)engine.current?.fit(true);},[isolatedBody]);
 const part=world.objects.find(o=>o.id===selected);
 return <section className="world-canvas"><div className="content-title">{sample?'Measured native poses':'Mechanical assembly · SI units'}<span className="spacer"/><button aria-pressed={native} onClick={()=>setNative(v=>!v)}>Native collision geometry</button><button onClick={()=>engine.current?.fit()}>Fit world</button>{visualContext?.world_roles.pivot&&<button onClick={()=>engine.current?.fit(false,true)}>Fit mechanism</button>}<button disabled={!part} onClick={()=>engine.current?.fit(true)}>Fit selected part</button><button onClick={()=>engine.current?.reset()}>Reset world camera</button></div><div ref={host} className="canvas-host" data-testid="world-canvas">{error&&<p role="alert">{error}</p>}</div>
  {part&&<div className="mechanical-inspection" data-testid="mechanical-inspection"><strong>{part.name}</strong><span>{part.dimensions_m.map(v=>Number(v.toPrecision(6))).join(' × ')} m · authoritative extents</span><span>{part.joint?`${part.joint.kind} · axis [${part.joint.axis.join(', ')}]`:part.parent?`Fixed to ${world.objects.find(o=>o.id===part.parent)?.name||part.parent}`:'Stationary / world parent'} · local rotation [{part.rotation_rad.map(v=>v.toFixed(3)).join(', ')}] rad</span><small>{part.id}</small></div>}
  <p className="note">{readOnly?'Read-only view.':'Select a component; drag handles to edit.'} Orbit, pan and zoom. {native?'Authoritative collision primitives; shape holes and omitted features are not modeled.':shapeParts?.length?'SHAPEBASE parametric surfaces; attachment axes are annotations. Physical proxies are separate.':MECHANICAL_ACCURACY}</p></section>;
}

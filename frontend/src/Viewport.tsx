import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import type {Sample,ArmSample,Scene,SceneObject} from './types';
import {MechanicalLibrary,recordedMechanicalSpec,disposeUnshared,MECHANICAL_ACCURACY} from './mechanicalVisuals';
import {Expand,RotateCcw,Grid3X3,Axis3D,Box,Scan} from 'lucide-react';

export function geometryFor(g:SceneObject):THREE.BufferGeometry{
 const [x,y,z]=g.size;
 if(g.type===6)return new THREE.BoxGeometry(x*2,y*2,z*2);
 if(g.type===0)return new THREE.PlaneGeometry(x*2,y*2); // finite display of declared plane extent
 if(g.type===2)return new THREE.SphereGeometry(x,24,16);
 if(g.type===3){const geometry=new THREE.CapsuleGeometry(x,y*2,8,20);geometry.rotateX(Math.PI/2);return geometry;}
 throw new Error('Unsupported compiled MuJoCo geometry: '+g.type);
}
export function measuredPosition(g:SceneObject,scene:Scene,sample:Sample|ArmSample):number[]{
 if(scene.family==='arm'){
  const pose=(sample as ArmSample).geom_poses?.[Number(g.id.split(':')[1])];
  if(!pose)throw new Error('Recorded articulated geom pose unavailable');return pose.position;
 }
 return g.position!.map((v,i)=>v+(g.moving?scene.slide_axis_world[i]*((sample as Sample).position-scene.reference_position):0));
}
export function measuredQuaternion(g:SceneObject,scene:Scene,sample:Sample|ArmSample):number[]{return scene.family==='arm'?(sample as ArmSample).geom_poses[Number(g.id.split(':')[1])].quaternion_wxyz:g.quaternion_wxyz!;}
function selectedGeom(g:SceneObject,id:string){return g.id===id||id===`body:${g.body}`||((id.startsWith('joint:')||id.startsWith('actuator:'))&&g.moving);}
export function replayBounds(scene:Scene,sample:Sample|ArmSample,selection?:string){
 const bounds=new THREE.Box3();
 for(const g of scene.geoms.filter(g=>g.type!==0&&(!selection||selectedGeom(g,selection)))){
  const geometry=geometryFor(g),mesh=new THREE.Mesh(geometry);
  mesh.position.fromArray(measuredPosition(g,scene,sample));const [w,x,y,z]=measuredQuaternion(g,scene,sample);mesh.quaternion.set(x,y,z,w);mesh.updateMatrixWorld(true);
  bounds.expandByObject(mesh);geometry.dispose();(mesh.material as THREE.Material).dispose();
 }
 return bounds;
}
export function fittedView(bounds:THREE.Box3,aspect:number,fov=42){
 const target=bounds.getCenter(new THREE.Vector3()),direction=new THREE.Vector3(.35,-1,.65).normalize();
 const right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,0,1),direction).normalize(),up=new THREE.Vector3().crossVectors(direction,right).normalize();
 let distance=.1,width=0,height=0;const tangent=Math.tan(THREE.MathUtils.degToRad(fov/2));
 for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
  const offset=new THREE.Vector3(x,y,z).sub(target),horizontal=Math.abs(offset.dot(right)),vertical=Math.abs(offset.dot(up)),depth=offset.dot(direction);
  width=Math.max(width,horizontal);height=Math.max(height,vertical);distance=Math.max(distance,horizontal/(tangent*aspect)+depth,vertical/tangent+depth);
 }
 return {target,position:target.clone().addScaledVector(direction,distance*1.15),halfHeight:Math.max(.15,height,width/aspect)*1.15};
}
export type CameraMemory={position:number[];target:number[];orthographicHalfHeight?:number};
export default function Viewport({scene,sample,selection,onSelect,visible,cameraMemory,scenario,minimumClearance}:{scene:Scene;sample:Sample|ArmSample;selection:string;onSelect:(id:string)=>void;visible:boolean;cameraMemory:React.RefObject<CameraMemory|null>;scenario?:string;minimumClearance?:number}){
 const host=useRef<HTMLDivElement>(null),labels=useRef<Record<string,HTMLDivElement|null>>({}),orientation=useRef<SVGSVGElement>(null),engine=useRef<{meshes:THREE.Object3D[];render:()=>void;select:(id:string)=>void;fit:(selected?:boolean)=>void;grid:THREE.GridHelper;axes:THREE.AxesHelper}|null>(null);
 const currentSample=useRef(sample);currentSample.current=sample;
 const currentSelect=useRef(onSelect);currentSelect.current=onSelect;
 const [projection,setProjection]=useState<'perspective'|'orthographic'>('perspective'),[grid,setGrid]=useState(true),[axes,setAxes]=useState(true),[error,setError]=useState(''),[native,setNative]=useState(false);
 useEffect(()=>{
  if(!host.current||!visible)return;
  const container=host.current;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}
  catch{setError('WebGL is unavailable. Measured telemetry remains available; no 3D rendering is claimed.');return;}
  setError('');
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));renderer.setClearColor(scene.family==='arm'&&document.documentElement.dataset.theme!=='dark'?'#eeefeb':'#191e23');renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.95;
  container.appendChild(renderer.domElement);
  const world=new THREE.Scene();world.up.set(0,0,1);
  const camera:THREE.PerspectiveCamera|THREE.OrthographicCamera=projection==='perspective'?new THREE.PerspectiveCamera(42,1,.01,100):new THREE.OrthographicCamera(-3,3,2,-2,.01,100);
  camera.up.set(0,0,1);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=false;controls.minDistance=.15;controls.maxDistance=25;
  let halfHeight=cameraMemory.current?.orthographicHalfHeight||2,selectedId=selection;
  const fit=(selected=false)=>{let bounds=replayBounds(scene,currentSample.current,selected?selectedId:undefined);if(bounds.isEmpty())bounds=replayBounds(scene,currentSample.current);const view=fittedView(bounds,Math.max(1,container.clientWidth)/Math.max(1,container.clientHeight));camera.position.copy(view.position);controls.target.copy(view.target);halfHeight=view.halfHeight;resize();camera.lookAt(controls.target);controls.update();render();};
  world.add(new THREE.HemisphereLight(0xe2e8ee,0x50565c,1.7));const light=new THREE.DirectionalLight(0xffffff,2.2);light.position.set(-1,-3,5);world.add(light);
  const library=new MechanicalLibrary();
  const meshes=scene.geoms.map(g=>{
   const spec=scene.family==='arm'&&!native?recordedMechanicalSpec(g,scene):null;
   const color=g.type===0?new THREE.Color(scene.family==='arm'?'#dfe4e2':'#252c31'):new THREE.Color(g.rgba[0],g.rgba[1],g.rgba[2]);
   const mesh=spec?library.create(spec):new THREE.Mesh(geometryFor(g),new THREE.MeshStandardMaterial({color,roughness:.65,metalness:.15,side:THREE.DoubleSide,wireframe:scene.family==='arm'&&native&&g.type!==0}));
   mesh.name=g.id;mesh.userData={...mesh.userData,...g};
   const [w,x,y,z]=measuredQuaternion(g,scene,currentSample.current);mesh.quaternion.set(x,y,z,w);
   mesh.position.fromArray(measuredPosition(g,scene,currentSample.current));world.add(mesh);return mesh;
  });
  const bounds=replayBounds(scene,currentSample.current),size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3());
  const gridSize=Math.ceil(Math.max(size.x,size.y)*1.15*2)/2;
  const gridObject=new THREE.GridHelper(gridSize,Math.round(gridSize/.25),scene.family==='arm'?0xaab8b6:0x46515b,scene.family==='arm'?0xd6ded9:0x323b43);gridObject.rotation.x=Math.PI/2;gridObject.position.set(center.x,center.y,.001);gridObject.visible=grid;world.add(gridObject);
  const axesObject=new THREE.AxesHelper(.5);axesObject.position.set(-.6,-.8,.01);axesObject.visible=axes;world.add(axesObject);
  const selectedBounds=new THREE.Box3(),outline=new THREE.Box3Helper(selectedBounds,0xe2a15d);outline.visible=false;world.add(outline);
  function render(){
   selectedBounds.makeEmpty();meshes.filter(mesh=>selectedGeom(mesh.userData as SceneObject,selectedId)&&mesh.userData.type!==0).forEach(mesh=>selectedBounds.expandByObject(mesh));outline.visible=!selectedBounds.isEmpty();
   renderer.render(world,camera);if(renderer.info){renderer.domElement.dataset.renderCalls=String(renderer.info.render.calls);renderer.domElement.dataset.triangles=String(renderer.info.render.triangles);renderer.domElement.dataset.geometries=String(renderer.info.memory.geometries);}
   for(const name of ['carriage_box','wall']){const label=labels.current[name],mesh=meshes.find(m=>m.userData.name===name);if(!label||!mesh)continue;const point=mesh.position.clone();point.z+=(mesh.userData.size[2]||0)+.08;point.project(camera);label.style.display=Math.abs(point.x)>1||Math.abs(point.y)>1||Math.abs(point.z)>1?'none':'block';label.style.transform=`translate(${(point.x+1)*container.clientWidth/2}px,${(1-point.y)*container.clientHeight/2}px) translate(-50%,-100%)`;}
   const inverse=camera.quaternion.clone().invert();[[1,0,0],[0,1,0],[0,0,1]].forEach((axis,i)=>{const projected=new THREE.Vector3(...axis).applyQuaternion(inverse),line=orientation.current?.querySelector(`[data-axis="${i}"]`),text=orientation.current?.querySelector(`[data-label="${i}"]`);line?.setAttribute('x2',String(32+projected.x*19));line?.setAttribute('y2',String(32-projected.y*19));text?.setAttribute('x',String(32+projected.x*25));text?.setAttribute('y',String(35-projected.y*25));});
  }
  const select=(id:string)=>{meshes.forEach(mesh=>{
   const selected=selectedGeom(mesh.userData as SceneObject,id);
   if(mesh instanceof THREE.Mesh)(mesh.material as THREE.MeshStandardMaterial).emissive.set(selected?0x3c2d1e:0x000000);
  });selectedId=id;render();};
  const resize=()=>{const width=Math.max(1,container.clientWidth),height=Math.max(1,container.clientHeight);renderer.setSize(width,height);if(camera instanceof THREE.PerspectiveCamera)camera.aspect=width/height;else{camera.left=-halfHeight*width/height;camera.right=halfHeight*width/height;camera.top=halfHeight;camera.bottom=-halfHeight;}camera.updateProjectionMatrix();render();};
  const observer=new ResizeObserver(resize);observer.observe(container);
  const changed=()=>{cameraMemory.current={position:camera.position.toArray(),target:controls.target.toArray(),orthographicHalfHeight:halfHeight};render();};controls.addEventListener('change',changed);
  const pointer=new THREE.Vector2(),raycaster=new THREE.Raycaster();let down=[0,0];
  const onDown=(event:PointerEvent)=>{down=[event.clientX,event.clientY];};
  const onClick=(event:PointerEvent)=>{if(Math.hypot(event.clientX-down[0],event.clientY-down[1])>4)return;const rect=renderer.domElement.getBoundingClientRect();pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(pointer,camera);const hit=raycaster.intersectObjects(meshes,true).find(h=>{let o=h.object;while(o.parent&&o.parent!==world)o=o.parent;return o.userData.name!=='floor';});if(hit){let object=hit.object;while(object.parent&&object.parent!==world)object=object.parent;currentSelect.current(object.name);}};
  renderer.domElement.addEventListener('pointerdown',onDown);renderer.domElement.addEventListener('pointerup',onClick);
  engine.current={meshes,render,select,fit,grid:gridObject,axes:axesObject};
  if(cameraMemory.current){camera.position.fromArray(cameraMemory.current.position);controls.target.fromArray(cameraMemory.current.target);controls.update();}else fit();
  resize();select(selection);
  return()=>{observer.disconnect();controls.removeEventListener('change',changed);controls.dispose();renderer.domElement.removeEventListener('pointerdown',onDown);renderer.domElement.removeEventListener('pointerup',onClick);meshes.forEach(disposeUnshared);library.dispose();outline.geometry.dispose();(outline.material as THREE.Material).dispose();gridObject.geometry.dispose();(gridObject.material as THREE.Material).dispose();axesObject.geometry.dispose();(axesObject.material as THREE.Material).dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();engine.current=null;};
 },[scene,projection,visible,native]);
 useEffect(()=>{if(engine.current){engine.current.grid.visible=grid;engine.current.axes.visible=axes;engine.current.render();}},[grid,axes]);
 useEffect(()=>{engine.current?.meshes.forEach((mesh,i)=>{mesh.position.fromArray(measuredPosition(scene.geoms[i],scene,sample));const [w,x,y,z]=measuredQuaternion(scene.geoms[i],scene,sample);mesh.quaternion.set(x,y,z,w);});engine.current?.render();},[sample,scene]);
 useEffect(()=>engine.current?.select(selection),[selection]);
 const inspected=scene.geoms.find(g=>selectedGeom(g,selection)&&g.type!==0),spec=inspected?recordedMechanicalSpec(inspected,scene):null;
 return <section className="viewport" aria-label="Recorded MuJoCo scene">
  <div className="viewport-toolbar"><span className="eyebrow">Scenario {scenario||'—'} <span className="toolbar-separator">/</span> {sample.time.toFixed(3)} s</span><span className="spacer"/>
   {scene.family==='arm'&&<button aria-pressed={native} title="Compiled primitives; joint and target marker spheres are non-colliding annotations" onClick={()=>setNative(v=>!v)}>Native geometry</button>}
   <button onClick={()=>engine.current?.fit()} title="Fit scene" aria-label="Fit scene"><Expand size={14}/></button>
   <button onClick={()=>{cameraMemory.current=null;engine.current?.fit();}} title="Reset camera" aria-label="Reset camera"><RotateCcw size={14}/></button>
   <button onClick={()=>engine.current?.fit(true)} title="Fit selected object" aria-label="Fit selected object"><Scan size={14}/></button>
   <button onClick={()=>setProjection(p=>p==='perspective'?'orthographic':'perspective')} title="Toggle projection" aria-label="Toggle projection"><Box size={14}/>{projection==='perspective'?'Perspective':'Orthographic'}</button>
   <button aria-pressed={grid} onClick={()=>setGrid(v=>!v)} title="Grid" aria-label="Grid"><Grid3X3 size={14}/></button>
   <button aria-pressed={axes} onClick={()=>setAxes(v=>!v)} title="Axes" aria-label="Axes"><Axis3D size={14}/></button>
  </div>
  <div className="canvas-host" ref={host}>{error&&<p className="canvas-error" role="alert">{error}</p>}{scene.geoms.some(g=>g.name==='carriage_box')&&<div className="scene-label" ref={node=>{labels.current.carriage_box=node;}}>Carriage</div>}{scene.geoms.some(g=>g.name==='wall')&&<div className="scene-label" ref={node=>{labels.current.wall=node;}}>Wall</div>}</div>
  {scene.family==='arm'&&<div className="mechanical-replay-inspection" data-testid="recorded-mechanical-inspection">{inspected&&<><strong>{inspected.name}</strong><span>{inspected.type===6?inspected.size.map((v:number)=>Number((v*2).toPrecision(6))).join(' × ')+' m · native box extents':'Native radius '+inspected.size[0]+' m'}</span><span>{spec?.identity.joint&&scene.joints.find(j=>j.id===spec.identity.joint)?.name} · {spec?.identity.body} · {inspected.id}</span><span>Measured quaternion [{measuredQuaternion(inspected,scene,sample).map(v=>v.toFixed(3)).join(', ')}]</span></>}<small>{native?'Native primitives.':MECHANICAL_ACCURACY}</small></div>}
  <div className="viewport-caption"><span title="Orbit: drag. Pan: right drag. Zoom: scroll.">Orbit / pan / zoom</span>{scene.family==='arm'?<span className="gap-overlay">Target error <code>{(sample as ArmSample).target_error_m.toFixed(4)} m</code></span>:<span className={'gap-overlay '+(minimumClearance!==undefined&&(sample as Sample).wall_clearance<minimumClearance?'danger':'')} title="Measured bumper-to-wall surface clearance">Surface gap <code>{(sample as Sample).wall_clearance.toFixed(4)} m</code></span>}</div>
  <svg ref={orientation} aria-hidden={!!error} className={'orientation-widget'+(error?' unavailable':'')} viewBox="0 0 64 64" aria-label="Camera orientation, world XYZ axes">{['X','Y','Z'].map((axis,i)=><g key={axis} className={'orientation-'+axis.toLowerCase()}><line data-axis={i} x1="32" y1="32" x2="32" y2="32"/><text data-label={i} x="32" y="32">{axis}</text></g>)}</svg>
 </section>;
}

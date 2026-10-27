import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {TransformControls} from 'three/examples/jsm/controls/TransformControls.js';
import type {Assembly,Part,Endpoint,Wire,Electrical} from './hardwareTypes';
import {diagnosticNets} from './circuitPresentation';
import {componentModel,endpointPosition,wireCurve} from './componentVisuals';
export {endpointPosition} from './componentVisuals';
export type CircuitSelection={kind:'pin';endpoint:Endpoint}|{kind:'wire';wireId:string}|null;
type Projection={pins:{endpoint:Endpoint;x:number;y:number;radius:number;connected:boolean}[];wires:{wire:Wire;path:string}[]};
export default function HardwareViewport({assembly,catalog,selection,onSelect,onTransform,mode,snap,visible,interaction=null,onInteraction,connecting=null,onTarget,diagnostics}:{assembly:Assembly;catalog:Record<string,Part>;selection:string;onSelect:(id:string)=>void;onTransform:(id:string,position:number[],rotation:number[])=>void;mode:'translate'|'rotate';snap:boolean;visible:boolean;interaction?:CircuitSelection;onInteraction?:(s:CircuitSelection)=>void;connecting?:Endpoint|null;onTarget?:(e:Endpoint)=>void;diagnostics?:Electrical|null}){
 const host=useRef<HTMLDivElement>(null),[error,setError]=useState(''),engine=useRef<any>(null),[projection,setProjection]=useState<Projection>({pins:[],wires:[]}),[hover,setHover]=useState<{label:string;x:number;y:number}|null>(null);
 const refs=useRef({assembly,selection,onSelect,onTransform,interaction,connecting,diagnostics});refs.current={assembly,selection,onSelect,onTransform,interaction,connecting,diagnostics};
 const memory=useRef<{position:number[];target:number[]}|null>(null);
 useEffect(()=>{
  if(!host.current||!visible)return;const container=host.current;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setError('3D unavailable. Use the component and pin inspector; visual verification is unavailable.');return;}
  const dark=document.documentElement.dataset.theme==='dark';renderer.setClearColor(dark?'#191e23':'#eeefeb');renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.appendChild(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,.001,100);camera.up.set(0,0,1);
  camera.position.fromArray(memory.current?.position||[.20,-.30,.38]);const orbit=new OrbitControls(camera,renderer.domElement);orbit.target.fromArray(memory.current?.target||[0,-.01,0]);orbit.update();
  scene.add(new THREE.HemisphereLight(0xffffff,0x8d9da6,2.3));const light=new THREE.DirectionalLight(0xffffff,2.5);light.position.set(.3,-.4,1);scene.add(light);
  const grid=new THREE.GridHelper(.6,60,dark?0x53616a:0xabbab9,dark?0x303b44:0xd7deda);grid.rotateX(Math.PI/2);grid.position.z=-.019;scene.add(grid);
  const gizmo=new TransformControls(camera,renderer.domElement);gizmo.setSize(.65);gizmo.setMode(mode);scene.add(gizmo.getHelper());
  let roots:THREE.Group[]=[],lines:THREE.Line[]=[],draft:THREE.Line|null=null,live=refs.current.assembly;
  const project=(p:number[])=>{const v=new THREE.Vector3(...p).project(camera);return {x:(v.x+1)*container.clientWidth/2,y:(1-v.y)*container.clientHeight/2,visible:v.z>-1&&v.z<1};};
  function render(){renderer.render(scene,camera);camera.updateMatrixWorld();
   const pins=live.components.flatMap(c=>catalog[c.part].pins.map(p=>{const endpoint={component:c.id,pin:p.id},xy=project(endpointPosition(live,catalog,endpoint));return {...xy,endpoint,connected:live.wires.some(w=>[w.a,w.b].some(e=>e.component===c.id&&e.pin===p.id)),radius:8};})).filter(p=>p.visible);
   for(const p of pins){const nearest=Math.min(...pins.filter(q=>q!==p).map(q=>Math.hypot(p.x-q.x,p.y-q.y)),100);p.radius=Math.min(8,nearest*.42);}
   setProjection({pins,wires:live.wires.map(w=>({wire:w,path:wireCurve(endpointPosition(live,catalog,w.a),endpointPosition(live,catalog,w.b)).getPoints(32).map((p,i)=>{const xy=project(p.toArray());return `${i?'L':'M'}${xy.x.toFixed(2)},${xy.y.toFixed(2)}`;}).join(' ')}))});
  }
  const dispose=(o:THREE.Object3D)=>{o.traverse(obj=>{const m=obj as THREE.Mesh;m.geometry?.dispose();if(m.material)(Array.isArray(m.material)?m.material:[m.material]).forEach(x=>x.dispose());});};
  const clear=()=>{gizmo.detach();for(const o of [...roots,...lines,...(draft?[draft]:[])]){scene.remove(o);dispose(o);}roots=[];lines=[];draft=null;};
  const wirePoints=(w:Wire)=>wireCurve(endpointPosition(live,catalog,w.a),endpointPosition(live,catalog,w.b)).getPoints(40);
  function previewTo(end:number[]){if(!refs.current.connecting)return;if(draft){scene.remove(draft);dispose(draft);}draft=new THREE.Line(new THREE.BufferGeometry().setFromPoints(wireCurve(endpointPosition(live,catalog,refs.current.connecting),end).getPoints(32)),new THREE.LineDashedMaterial({color:'#d47c55',dashSize:.003,gapSize:.002}));draft.computeLineDistances();scene.add(draft);}
  function update(){clear();live=refs.current.assembly;const failures=diagnosticNets(live,refs.current.diagnostics),selected=refs.current.selection,interaction=refs.current.interaction,chosen=interaction?.kind==='wire'?live.wires.find(w=>w.id===interaction.wireId):null;
   for(const c of live.components){const root=componentModel(catalog[c.part]);root.name=c.id;root.position.fromArray(c.position_m);root.rotation.set(...c.rotation_rad as [number,number,number],'XYZ');
    if(c.id===selected){const outline=new THREE.BoxHelper(root,0x356b86);root.updateMatrixWorld();scene.add(root);scene.add(outline);root.userData.outline=outline;}else scene.add(root);roots.push(root);
    for(const obj of root.children){const p=obj.userData.pin;if(p&&!obj.userData.hitTarget){const selectedPin=interaction?.kind==='pin'&&interaction.endpoint.component===c.id&&interaction.endpoint.pin===p;const netPin=chosen&&[chosen.a,chosen.b].some(e=>e.component===c.id&&e.pin===p);if(selectedPin||netPin)((obj as THREE.Mesh).material as THREE.MeshStandardMaterial).color.set('#d47c55');}}
   }
   for(const w of live.wires){const p=catalog[live.components.find(c=>c.id===w.a.component)!.part].pins.find(p=>p.id===w.a.pin)!,role=live.components.find(c=>c.id===w.a.component)!.roles[p.id]||p.role;
    const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(wirePoints(w)),new THREE.LineBasicMaterial({color:failures.has(w.net)?'#b52f35':chosen?.net===w.net?'#ce6d44':role.includes('power')?'#b15d4a':role==='ground'?'#65736c':'#447f97'}));line.userData=w;scene.add(line);lines.push(line);
   }
   const selectedRoot=roots.find(r=>r.name===selected);if(selectedRoot&&!refs.current.connecting&&!interaction)gizmo.attach(selectedRoot);
   if(refs.current.connecting&&interaction?.kind==='pin'&&(interaction.endpoint.component!==refs.current.connecting.component||interaction.endpoint.pin!==refs.current.connecting.pin))previewTo(endpointPosition(live,catalog,interaction.endpoint));render();
  }
  // Dispose outlines separately because they live in the scene rather than body space.
  const originalClear=clear;
  function refresh(){for(const r of roots){const o=r.userData.outline;if(o){scene.remove(o);dispose(o);}}update();}
  gizmo.addEventListener('dragging-changed',e=>{orbit.enabled=!e.value;});
  gizmo.addEventListener('objectChange',()=>{const object=gizmo.object;if(!object)return;live={...refs.current.assembly,components:refs.current.assembly.components.map(c=>c.id===object.name?{...c,position_m:object.position.toArray(),rotation_rad:[object.rotation.x,object.rotation.y,object.rotation.z]}:c)};
   for(const line of lines)line.geometry.setFromPoints(wirePoints(line.userData as Wire));object.userData.outline?.update();render();});
  gizmo.addEventListener('mouseUp',()=>{const o=gizmo.object;if(o)refs.current.onTransform(o.name,o.position.toArray(),[o.rotation.x,o.rotation.y,o.rotation.z]);});
  let down={x:0,y:0};const pointerDown=(e:PointerEvent)=>{down={x:e.clientX,y:e.clientY};};
  const pointerUp=(e:PointerEvent)=>{if(gizmo.axis||Math.hypot(e.clientX-down.x,e.clientY-down.y)>4)return;const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera);const hit=ray.intersectObjects(roots,true)[0];if(hit){let object=hit.object;while(object.parent&&object.parent!==scene)object=object.parent;refs.current.onSelect(object.name);}};
  const preview=(e:PointerEvent)=>{if(!refs.current.connecting)return;const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(2*(e.clientX-rect.left)/rect.width-1,1-2*(e.clientY-rect.top)/rect.height),camera);const end=new THREE.Vector3();if(!ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,0,1),0),end))return;
   previewTo(end.toArray());render();};
  renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointerup',pointerUp);renderer.domElement.addEventListener('pointermove',preview);orbit.addEventListener('change',render);gizmo.addEventListener('change',render);
  const themeChange=()=>{renderer.setClearColor(document.documentElement.dataset.theme==='dark'?'#191e23':'#eeefeb');render();};window.addEventListener('embody-theme-change',themeChange);
  const resize=()=>{camera.aspect=Math.max(1,container.clientWidth)/Math.max(1,container.clientHeight);camera.updateProjectionMatrix();renderer.setSize(Math.max(1,container.clientWidth),Math.max(1,container.clientHeight));render();};const observer=new ResizeObserver(resize);observer.observe(container);
  const fit=()=>{const bounds=new THREE.Box3();roots.forEach(o=>bounds.expandByObject(o));if(bounds.isEmpty())return;const center=bounds.getCenter(new THREE.Vector3()),span=Math.max(...bounds.getSize(new THREE.Vector3()).toArray(),.05),distance=span/(2*Math.tan(THREE.MathUtils.degToRad(camera.fov/2)))*1.4/Math.min(camera.aspect,1);camera.position.copy(center).addScaledVector(new THREE.Vector3(.25,-.65,1).normalize(),distance);orbit.target.copy(center);orbit.update();render();};
  engine.current={update:refresh,gizmo,fit,previewPin:(endpoint:Endpoint)=>{previewTo(endpointPosition(live,catalog,endpoint));render();},reset:()=>{memory.current=null;camera.position.set(.20,-.30,.38);orbit.target.set(0,-.01,0);orbit.update();render();}};update();resize();if(!memory.current)fit();
  return()=>{memory.current={position:camera.position.toArray(),target:orbit.target.toArray()};engine.current=null;observer.disconnect();window.removeEventListener('embody-theme-change',themeChange);for(const r of roots){const o=r.userData.outline;if(o){scene.remove(o);dispose(o);}}originalClear();gizmo.dispose();orbit.dispose();renderer.dispose();renderer.domElement.remove();grid.geometry.dispose();(grid.material as THREE.Material).dispose();};
 },[catalog,visible]);
 const componentCount=useRef(assembly.components.length);
 useEffect(()=>{engine.current?.update();if(componentCount.current!==assembly.components.length){engine.current?.fit();componentCount.current=assembly.components.length;}},[assembly,selection,interaction,connecting,visible,diagnostics]);
 useEffect(()=>{const g=engine.current?.gizmo;if(g){g.setMode(mode);g.setTranslationSnap(snap ? .005 : null);g.setRotationSnap(snap?Math.PI/12:null);}},[mode,snap,visible]);
 const name=(e:Endpoint)=>assembly.components.find(c=>c.id===e.component)?.name+' · '+e.pin;
 return <section className="hardware-canvas"><div className="content-title"><span>Assembly <small> / approximate component models</small></span><span className="spacer"/><button onClick={()=>engine.current?.fit()}>Fit assembly</button><button onClick={()=>engine.current?.reset()}>Reset camera</button></div><div className="canvas-host" ref={host} data-testid="hardware-canvas">
  {error&&<p role="alert">{error}</p>}
  <svg className="wire-hit-layer" aria-label="3D circuit connections">{projection.wires.map(({wire:w,path})=><path key={w.id} d={path} data-wire-id={w.id} data-net-id={w.net} role="button" tabIndex={0} aria-label={`Inspect wire ${w.a.component}.${w.a.pin} to ${w.b.component}.${w.b.pin}`} onPointerEnter={e=>setHover({label:`${w.a.component}.${w.a.pin} → ${w.b.component}.${w.b.pin} · ${w.net}`,x:e.nativeEvent.offsetX,y:e.nativeEvent.offsetY})} onPointerLeave={()=>setHover(null)} onClick={()=>onInteraction?.({kind:'wire',wireId:w.id})} onKeyDown={e=>{if(e.key==='Enter'||e.key===' ')onInteraction?.({kind:'wire',wireId:w.id});}}/>)}</svg>
  <div className="pin-hit-layer">{projection.pins.map(p=><button key={p.endpoint.component+'.'+p.endpoint.pin} className={'pin-target '+(interaction?.kind==='pin'&&interaction.endpoint.component===p.endpoint.component&&interaction.endpoint.pin===p.endpoint.pin?'active':'')} data-endpoint={p.endpoint.component+'.'+p.endpoint.pin} aria-label={'Pin '+p.endpoint.component+'.'+p.endpoint.pin} style={{left:p.x,top:p.y,width:p.radius*2,height:p.radius*2}} onPointerEnter={()=>{setHover({label:`${name(p.endpoint)} · ${p.connected?'Connected':'Unconnected'}`,x:p.x,y:p.y});if(connecting)engine.current?.previewPin(p.endpoint);}} onPointerLeave={()=>setHover(null)} onFocus={()=>setHover({label:name(p.endpoint),x:p.x,y:p.y})} onBlur={()=>setHover(null)} onClick={()=>{onInteraction?.({kind:'pin',endpoint:p.endpoint});if(connecting)onTarget?.(p.endpoint);}}/> )}</div>
  {hover&&<div role="tooltip" className="circuit-tooltip" style={{left:Math.max(6,Math.min(hover.x+12,(host.current?.clientWidth||600)-260)),top:Math.max(8,Math.min(hover.y-48,(host.current?.clientHeight||400)-60))}}>{hover.label}</div>}
  <div className="canvas-hint">{connecting?`Connecting ${connecting.component}.${connecting.pin} · choose a pin`:'Drag to orbit · Shift to pan · Scroll to zoom'}</div>
 </div></section>;
}

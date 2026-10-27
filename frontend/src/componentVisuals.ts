import * as THREE from 'three';
import type {Part,Assembly,Endpoint} from './hardwareTypes';

type Vec=[number,number,number];
export type VisualMesh={name:string;shape:'box'|'cylinder'|'sphere';size:Vec;position:Vec;rotation?:Vec;color:string;metalness?:number};
export type ComponentVisualSpec={catalogId:string;version:1;assetId:string;origin:'CATALOG_LOCAL_SI';dimensions:Vec;accuracy:string;meshes:VisualMesh[];pins:{id:string;position:Vec;hitRadius:number;label:Vec}[];selectionBounds:Vec;detailLevels:['standard','fallback'];fallback:boolean;provenance:string};
const supported=['hcsr04_sen15569','esp32_devkitc_v4_wroom32','towerpro_sg90_digital','resistor_2200','resistor_3300','regulated_dual_supply','connector_2'];
export function visualSpec(part:Part):ComponentVisualSpec{
 const size=part.size_m as Vec,meshes:VisualMesh[]=[];
 const box=(name:string,size:Vec,position:Vec,color:string,metalness=0)=>meshes.push({name,shape:'box',size,position,color,metalness});
 const cylinder=(name:string,r:number,height:number,position:Vec,color:string,rotation:Vec=[Math.PI/2,0,0],metalness=.5)=>meshes.push({name,shape:'cylinder',size:[r,r,height],position,rotation,color,metalness});
 const [x,y,z]=size;
 if(part.kind==='sensor'){
  box('blue-pcb',[x,y,.0016],[0,0,-.003],'#236d8b');
  for(const px of [-.012,.012]){cylinder('metal-transducer',.0078,.011,[px,.001,.0035],'#bfcbd0');cylinder('dark-transducer-face',.0063,.0008,[px,.001,.0095],'#33434b');cylinder('mesh-center',.0048,.0009,[px,.001,.0101],'#687e88');}
  box('controller-chip',[.006,.004,.002],[0,-.006,-.001],'#242c2e');
 }else if(part.kind==='board'){
  box('development-pcb',[x,y,.0016],[0,0,-.002],'#255d55');box('radio-shield',[.018,.017,.003],[.005,0,.001],'#bec5c5',.7);box('antenna',[.012,.018,.002],[.02,0,.0005],'#313a3c');
  for(let i=0;i<5;i++)box('antenna-trace',[.0007,.012,.0002],[.016+i*.002,0,.0017],'#bd9b55',.7);
  box('usb-connector',[.008,.009,.005],[-.025,0,.001],'#bac6cb',.8);box('usb-opening',[.0005,.006,.002],[-.0291,0,.001],'#263438');
  for(const py of [-.0105,.0105]){box('header-socket',[.048,.0028,.003],[.001,py,-.0002],'#252f33');for(let i=0;i<19;i++)box('decorative-header-contact',[.0007,.001,.0006],[-.023+i*.00254,py,.0016],'#c2a66b',.8);}
  box('reset-button',[.003,.003,.002],[-.017,-.006,0],'#d2d5d2');box('boot-button',[.003,.003,.002],[-.017,.006,0],'#d2d5d2');
 }else if(part.kind==='servo'){
  box('servo-case',[x,y,z*.72],[0,.002,z*.18],'#247ab0');box('servo-cap',[x*.9,y*.9,z*.18],[0,.002,z*.62],'#4099c6');
  box('mounting-flange',[x*1.35,y*.8,.002],[0,.002,z*.36],'#286e9f');cylinder('output-hub',.0035,.004,[-.005,.002,z*.78],'#e8e5d9');
  box('servo-horn',[.022,.0035,.0018],[-.005,.002,z*.87],'#f3f0e5');cylinder('horn-screw',.0012,.002,[-.005,.002,z*.9],'#6d7b82');
 }else if(part.kind==='resistor'){
  cylinder('axial-body',.002,.010,[0,0,0],'#cbb48b',[0,0,Math.PI/2],0);
  const bands=part.id==='resistor_2200'?['#b83e35','#b83e35','#9a592c','#b59a4c']:['#d47c29','#d47c29','#9a592c','#b59a4c'];
  bands.forEach((c,i)=>cylinder('resistor-band',.00203,.0006,[-.003+i*.002,0,0],c,[0,0,Math.PI/2],0));
  box('axial-lead',[.016,.00055,.00055],[0,0,0],'#b4c2c8',.8);
 }else if(part.kind==='supply'){
  box('ideal-supply-case',[x,y,z],[0,0,z*.25],'#e0ded5');box('supply-face',[x*.9,y*.83,.001],[0,0,z*.77],'#384d58');
  box('power-indicator',[.003,.002,.0005],[-.012,.005,z*.81],'#71b896');
 }else if(part.kind==='connector'){
  box('terminal-housing',[x,y,z],[0,.001,z*.35],'#4a896e');
  for(const px of [-.004,.004]){cylinder('terminal-screw',.002,.001,[px,.001,z*.9],'#b4c2c8');box('screw-slot',[.0028,.00045,.0002],[px,.001,z*.97],'#48565a');}
 }else box('approximate-fallback',size,[0,0,0],'#85979c');
 const pins=part.pins.map(p=>{
  const nearest=Math.min(...part.pins.filter(q=>q.id!==p.id).map(q=>new THREE.Vector3(...p.position_m).distanceTo(new THREE.Vector3(...q.position_m))),.01);
  return {id:p.id,position:[...p.position_m] as Vec,hitRadius:Math.min(.0032,nearest*.38),label:[p.position_m[0],p.position_m[1]-.003,p.position_m[2]] as Vec};
 });
 const spec:ComponentVisualSpec={catalogId:part.id,version:1,assetId:'embody-procedural-v1/'+part.id,origin:'CATALOG_LOCAL_SI',dimensions:[...size],accuracy:'Approximate body detail and illustrative catalog pin coordinates; not a validated footprint. '+String(part.properties.dimensions_status||'ILLUSTRATIVE'),meshes,pins,selectionBounds:[x*1.4,y*1.2,z*2],detailLevels:['standard','fallback'],fallback:!supported.includes(part.id),provenance:'Locally authored procedural geometry; catalog sizes/identities unchanged. No downloaded asset.'};
 validateVisualSpec(spec,part);return spec;
}
export function validateVisualSpec(spec:ComponentVisualSpec,part:Part){
 if(spec.catalogId!==part.id||new Set(spec.pins.map(p=>p.id)).size!==spec.pins.length||spec.pins.length!==part.pins.length)throw new Error('Missing or duplicate visual pin anchor');
 for(const p of part.pins){const a=spec.pins.find(a=>a.id===p.id);if(!a||a.position.some((v,i)=>!Number.isFinite(v)||v!==p.position_m[i]))throw new Error('Visual anchor differs from authoritative catalog');}
}
export function componentModel(part:Part):THREE.Group{
 const group=new THREE.Group(),spec=visualSpec(part);group.userData.visualSpec=spec;
 for(const m of spec.meshes){let geometry:THREE.BufferGeometry;
  if(m.shape==='cylinder')geometry=new THREE.CylinderGeometry(m.size[0],m.size[1],m.size[2],24);else if(m.shape==='sphere')geometry=new THREE.SphereGeometry(m.size[0],12,8);else geometry=new THREE.BoxGeometry(...m.size);
  const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:m.color,metalness:m.metalness||0,roughness:.52}));mesh.name=m.name;mesh.position.fromArray(m.position);if(m.rotation)mesh.rotation.set(...m.rotation);group.add(mesh);
 }
 for(const p of spec.pins){const pin=new THREE.Mesh(new THREE.SphereGeometry(.00125,12,8),new THREE.MeshStandardMaterial({color:'#d6b16b',metalness:.7,roughness:.4}));pin.position.fromArray(p.position);pin.name='pin:'+p.id;pin.userData.pin=p.id;group.add(pin);
  const hit=new THREE.Mesh(new THREE.SphereGeometry(p.hitRadius,10,8),new THREE.MeshBasicMaterial({visible:false}));hit.position.copy(pin.position);hit.userData.pin=p.id;hit.userData.hitTarget=true;group.add(hit);
 }
 return group;
}
export function endpointPosition(a:Assembly,catalog:Record<string,Part>,e:Endpoint):number[]{
 const c=a.components.find(c=>c.id===e.component),p=c&&catalog[c.part]?.pins.find(p=>p.id===e.pin);if(!c||!p)throw new Error('Absent wiring endpoint');
 return new THREE.Vector3(...p.position_m).applyEuler(new THREE.Euler(...c.rotation_rad as Vec,'XYZ')).add(new THREE.Vector3(...c.position_m)).toArray();
}
export function wireCurve(a:number[],b:number[]):THREE.CatmullRomCurve3{
 const start=new THREE.Vector3(...a),end=new THREE.Vector3(...b),lift=Math.min(.035,start.distanceTo(end)*.22+.006);
 return new THREE.CatmullRomCurve3([start,start.clone().lerp(end,.28).add(new THREE.Vector3(0,0,lift)),start.clone().lerp(end,.72).add(new THREE.Vector3(0,0,lift)),end]);
}

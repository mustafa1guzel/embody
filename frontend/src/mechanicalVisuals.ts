/** Display-only engineering parts. All dimensions are metres; never collision data. */
import * as THREE from 'three';
import type {World,WorldObject} from './engineeringTypes';
import type {Scene,SceneObject} from './types';
export type Vec3=[number,number,number];
export type MechanicalIdentity={body:string;geom?:string;joint?:string;link?:string;actuator?:string;mount?:string;sensor?:string;component?:string};
export type MechanicalSpec={kind:'link'|'joint'|'actuator'|'support'|'plate'|'sensor_mount';dimensions:Vec3;identity:MechanicalIdentity;axis?:Vec3;endpointSpan?:boolean;housingDiameter?:number};
export type MechanicalContext={world_roles:Record<string,string>;component_roles:Record<string,string>};
export const MECHANICAL_ACCURACY='Illustrative housings, holes and fasteners; not collision geometry, manufactured parts or modeled internals.';
const colors={alloy:'#b9c7cd',edge:'#e2e7e6',dark:'#3d515c',inset:'#718590',accent:'#367c89',shaft:'#bba36c'};
export function validateMechanicalSpec(s:MechanicalSpec){
 if(!['link','joint','actuator','support','plate','sensor_mount'].includes(s.kind)||!s.identity.body||s.dimensions.length!==3||s.dimensions.some(x=>!Number.isFinite(x)||x<=0||x>100))throw new Error('Mechanical visual requires finite positive SI dimensions and body identity');
 if(s.axis&&(s.axis.length!==3||s.axis.some(x=>!Number.isFinite(x))||Math.abs(new THREE.Vector3(...s.axis).length()-1)>1e-6))throw new Error('Mechanical axis must be a unit vector');
 if(s.housingDiameter!==undefined&&(!Number.isFinite(s.housingDiameter)||s.housingDiameter<=0||s.housingDiameter>100))throw new Error('Invalid visual housing diameter');
}
export function roundedPlate(length:number,width:number,thickness:number,holes:{x:number;y:number;r:number}[]=[]){
 if(![length,width,thickness].every(x=>Number.isFinite(x)&&x>0)||length<width)throw new Error('Invalid rounded plate dimensions');
 const x=length/2,y=width/2,r=Math.min(width/2,length/2),shape=new THREE.Shape();
 shape.moveTo(-x+r,-y);shape.lineTo(x-r,-y);shape.quadraticCurveTo(x,-y,x,-y+r);shape.lineTo(x,y-r);shape.quadraticCurveTo(x,y,x-r,y);shape.lineTo(-x+r,y);shape.quadraticCurveTo(-x,y,-x,y-r);shape.lineTo(-x,-y+r);shape.quadraticCurveTo(-x,-y,-x+r,-y);
 for(const h of holes){if(![h.x,h.y,h.r].every(Number.isFinite)||h.r<=0||Math.abs(h.x)+h.r>=x||Math.abs(h.y)+h.r>=y)throw new Error('Hole outside bounded plate');const path=new THREE.Path();path.absarc(h.x,h.y,h.r,0,Math.PI*2,true);shape.holes.push(path);}
 const bevel=Math.min(thickness*.12,width*.025);
 const g=new THREE.ExtrudeGeometry(shape,{depth:thickness-2*bevel,bevelEnabled:true,bevelSegments:1,steps:1,bevelSize:bevel,bevelThickness:bevel,curveSegments:8});g.translate(0,0,-thickness/2+bevel);return g;
}
/** Per-viewport bounded cache. Selection never mutates shared materials. */
export class MechanicalLibrary{
 private geometries=new Map<string,THREE.BufferGeometry>();private materials=new Map<string,THREE.MeshStandardMaterial>();
 private geometry(key:string,make:()=>THREE.BufferGeometry){let g=this.geometries.get(key);if(!g){g=make();g.userData.mechanicalShared=true;if(this.geometries.size<128)this.geometries.set(key,g);else g.userData.mechanicalShared=false;}return g;}
 private material(color:string){let m=this.materials.get(color);if(!m){m=new THREE.MeshStandardMaterial({color,roughness:.42,metalness:color===colors.shaft?.65:.35,side:THREE.DoubleSide});m.userData.mechanicalShared=true;this.materials.set(color,m);}return m;}
 create(s:MechanicalSpec):THREE.Group{
  validateMechanicalSpec(s);const root=new THREE.Group();root.userData={mechanicalSpec:structuredClone(s),semantic:structuredClone(s.identity),accuracy:MECHANICAL_ACCURACY};
  const [x,y,z]=s.dimensions;
  const mesh=(name:string,geometry:THREE.BufferGeometry,color:string,position:Vec3=[0,0,0],parent:THREE.Group=root)=>{const m=new THREE.Mesh(geometry,this.material(color));m.name=name;m.position.fromArray(position);m.userData={semantic:structuredClone(s.identity),objectId:s.identity.body,displayOnly:true};parent.add(m);return m;};
  const box=(name:string,size:Vec3,position:Vec3,color:string,parent=root)=>mesh(name,this.geometry('box/'+size.join(','),()=>new THREE.BoxGeometry(...size)),color,position,parent);
  const cylinder=(name:string,r:number,h:number,position:Vec3,color:string,parent=root)=>mesh(name,this.geometry(`cylinder/${r}/${h}`,()=>new THREE.CylinderGeometry(r,r,h,24).rotateX(Math.PI/2)),color,position,parent);
  const plate=(name:string,l:number,w:number,t:number,position:Vec3,color:string,holes:{x:number;y:number;r:number}[]=[],parent=root)=>mesh(name,this.geometry('plate/'+JSON.stringify([l,w,t,holes]),()=>roundedPlate(l,w,t,holes)),color,position,parent);
  const bolts=(l:number,w:number,height:number,scale:number,parent=root)=>{for(const px of [-l*.34,l*.34])for(const py of [-w*.31,w*.31]){cylinder('mount-fastener',scale,height*.25,[px,py,height*.6],colors.shaft,parent);box('fastener-slot',[scale*1.2,scale*.18,height*.03],[px,py,height*.74],colors.dark,parent);}};
  if(s.kind==='link'){
   const width=Math.min(y,x*.35),length=s.endpointSpan?x+width:x,ends=s.endpointSpan?x/2:x/2-width*.7,hole=width*.16;
   plate('rounded-link-with-through-holes',length,width,z,[0,0,0],colors.alloy,[{x:-ends,y:0,r:hole},{x:ends,y:0,r:hole}]);
   plate('link-face-recess',Math.max(width,x-width*1.7),width*.42,z*.09,[0,0,z*.51],colors.dark);
   // Decorative edge land, not a second load-bearing link or extra modeled mass.
   root.userData.attachmentCenters=[[-ends,0,0],[ends,0,0]];
  }else if(s.kind==='joint'||s.kind==='actuator'){
   const d=s.housingDiameter??Math.max(x,y),h=Math.max(z,d*.44),module=new THREE.Group();module.name='axis-aligned-joint-module';module.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),new THREE.Vector3(...(s.axis||[0,0,1])));root.add(module);
   if(s.kind==='actuator'){
    box('actuator-housing',[d*1.35,d*1.25,h*.85],[0,0,-h*.75],colors.dark,module);
    plate('actuator-mounting-flange',d*1.7,d*1.25,h*.15,[0,0,-h*1.2],colors.alloy,[],module);const flange=new THREE.Group();flange.position.z=-h*1.2;module.add(flange);bolts(d*1.7,d*1.25,h*.14,d*.06,flange);
   }
   cylinder('joint-bearing-housing',d*.5,h,[0,0,0],colors.dark,module);cylinder('bearing-sleeve',d*.43,h*.18,[0,0,h*.54],colors.alloy,module);
   cylinder('axis-coupling',d*.28,h*.24,[0,0,h*.65],colors.accent,module);cylinder('shaft',d*.13,h*1.5,[0,0,h*.17],colors.shaft,module);
   for(let i=0;i<4;i++){const a=i*Math.PI/2;cylinder('bearing-cap-fastener',d*.042,h*.1,[Math.cos(a)*d*.35,Math.sin(a)*d*.35,h*.66],colors.edge,module);}
   box('coupling-orientation-key',[d*.22,d*.055,h*.025],[0,0,h*.94],colors.dark,module);
  }else if(s.kind==='support'){
   box('structural-upright',[x*.88,y*.88,z],[0,0,0],colors.alloy);
   plate('mounting-foot',Math.max(x,y)*1.35,Math.min(x,y)*1.2,Math.min(z*.1,x*.16),[0,0,-z/2],colors.dark);
   plate('support-cap',Math.max(x,y)*1.12,Math.min(x,y),Math.min(z*.05,x*.1),[0,0,z/2],colors.dark);
   for(const px of [-x*.28,x*.28])box('upright-machining-land',[x*.08,y*.02,z*.72],[px,-y*.45,0],colors.inset);
   const foot=new THREE.Group();foot.position.z=-z/2;root.add(foot);bolts(Math.max(x,y)*1.35,Math.min(x,y)*1.2,Math.min(z*.1,x*.16),Math.min(x,y)*.055,foot);
  }else{
   // Plate and mounting cradle have finite through-holes and explicit local axes.
   const l=Math.max(x,y),w=Math.min(x,y),t=Math.min(z,l*.12),base=new THREE.Group();if(y>x)base.rotation.z=Math.PI/2;root.add(base);
   const holes=[-1,1].flatMap(a=>[-1,1].map(b=>({x:a*l*.33,y:b*w*.28,r:w*.06})));
   plate('drilled-mounting-plate',l,w,t,[0,0,-z/2+t/2],colors.alloy,holes,base);
   if(s.kind==='sensor_mount'){
    for(const py of [-w*.44,w*.44])box('sensor-cradle-ear',[l*.84,w*.12,z*.7],[0,py,0],colors.dark,base);
    box('mount-crosspiece',[l*.12,w*.8,z*.5],[-l*.43,0,0],colors.accent,base);
   }else box('mounting-standoff',[l*.42,w*.4,z*.65],[0,0,0],colors.dark,base);
  }
  return root;
 }
 dispose(){for(const g of this.geometries.values())g.dispose();for(const m of this.materials.values())m.dispose();this.geometries.clear();this.materials.clear();}
 get cacheSize(){return this.geometries.size;}
}
export function disposeUnshared(object:THREE.Object3D){object.traverse(o=>{const m=o as THREE.Mesh;if(m.geometry&&!m.geometry.userData.mechanicalShared)m.geometry.dispose();if(m.material)for(const mat of Array.isArray(m.material)?m.material:[m.material])if(!mat.userData.mechanicalShared)mat.dispose();});}
/** Classification uses actual typed world state and optional preserved creation roles. */
export function worldMechanicalSpec(o:WorldObject,w:World,context?:MechanicalContext):MechanicalSpec|null{
 const role=Object.entries(context?.world_roles||{}).find(([,id])=>id===o.id)?.[0];
 const identity:MechanicalIdentity={body:o.id,geom:'geom_'+o.id};
 if(o.joint)identity.joint='joint_'+o.id;if(o.actuator)identity.actuator='motor_'+o.id;
 if(role==='pivot'){identity.component=context?.component_roles.servo;if(o.parent)identity.mount=o.parent;}
 const dims=[...o.dimensions_m] as Vec3;
 if(role==='sensor'){identity.sensor=o.id;identity.mount=o.id;identity.component=context?.component_roles.sensor;return {kind:'sensor_mount',dimensions:dims,identity};}
 if(role==='board_mount'){identity.mount=o.id;identity.component=context?.component_roles.board;return {kind:'plate',dimensions:dims,identity};}
 if(o.joint?.kind==='revolute'){
  const child=w.objects.find(c=>c.parent===o.id&&c.kind==='link');const housingDiameter=Math.max(...dims,child?Math.max(child.dimensions_m[1],child.dimensions_m[2])*1.7:0);
  return {kind:o.actuator?'actuator':'joint',dimensions:dims,identity,axis:[...o.joint.axis] as Vec3,housingDiameter};
 }
 if(o.kind==='link'&&o.geometry==='box'&&dims[0]>=dims[1]*2){identity.link=o.id;const parent=w.objects.find(p=>p.id===o.parent);if(parent?.joint)identity.joint='joint_'+parent.id;return {kind:'link',dimensions:dims,identity};}
 if(o.kind==='anchor'&&o.geometry==='box'){identity.mount=o.id;return {kind:dims[2]>Math.max(dims[0],dims[1])?'support':'plate',dimensions:dims,identity};}
 return null;
}
/** Bounded adapter for the existing named two-link arm; unknown geoms stay native. */
export function recordedMechanicalSpec(g:SceneObject,scene?:Scene):MechanicalSpec|null{
 const dims=g.type===6?g.size.map((v:number)=>v*2):g.type===2?[g.size[0]*2,g.size[0]*2,g.size[0]*2]:null;
 if(!dims)return null;
 const identity:MechanicalIdentity={body:g.body!==undefined?'body:'+g.body:g.id,geom:g.id};
 if(scene?.family==='arm'){
  const link=g.name==='link1_box'?0:g.name==='link2_box'?1:-1;
  const marker=g.name==='shoulder_marker'?0:g.name==='elbow_marker'?1:-1;
  const index=Math.max(link,marker),joint=scene.joints[index],actuator=scene.actuators[index];
  if(index>=0&&joint&&actuator){identity.joint=joint.id;identity.actuator=actuator.id;
   if(link>=0){identity.link=identity.body;return {kind:'link',dimensions:dims as Vec3,identity,endpointSpan:true};}
   return {kind:'actuator',dimensions:dims as Vec3,identity,axis:[...joint.axis] as Vec3};
  }
  if(g.name==='arm_mount'){identity.mount=identity.body;return {kind:'support',dimensions:dims as Vec3,identity};}
 }
 // Names are from the existing trusted reference device compiler, not inferred capabilities.
 if(!scene){
  if(g.name==='beam'){identity.body='barrier';identity.link='barrier';identity.joint='hinge';identity.actuator='ideal_servo';return {kind:'link',dimensions:dims as Vec3,identity};}
  if(g.name==='base'){identity.mount=g.id;return {kind:'support',dimensions:dims as Vec3,identity};}
  if(g.name==='sensor_marker'){identity.sensor=g.id;identity.mount=g.id;return {kind:'sensor_mount',dimensions:dims as Vec3,identity};}
 }
 return null;
}

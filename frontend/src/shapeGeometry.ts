/** Backend-authoritative SHAPEBASE profiles; no parameter edits or physics here. */
import * as THREE from 'three';
export type ShapeHole={id:string;diameter_m:number;u:number;v:number};
export type ShapeFrame={id:string;source:string;hole_id:string|null;rotation_rad:number[]};
export type ShapeSpec={schema_version:1;id:string;body_id:string;assembly_id:string;family:string;geometry_revision:number;units:'SI';parameters:Record<string,number>;parent_body_id:string|null;position_m:number[];rotation_rad:number[];mounting_holes:ShapeHole[];attachment_frames:ShapeFrame[];joint_attachment:{joint_body_id:string;frame_id:string}|null;frame_attachment?:{mount_body_id:string;frame_id:string};mounted_bodies:{body_id:string;frame_id:string}[];physical:{representation:string;accuracy:string;mass_kg:number;mass_source:string;density_source:string;inertia_source:string;included_features:string[];omitted_features:string[]};visual:Record<string,unknown>};
export type GeneratedHole={id:string;center_m:number[];radius_m:number};
export type ShapeGeometry={shape_id:string;body_id:string;geometry_revision:number;shape_sha256:string;representation:string;dimensions_m:number[];sections:{id:string;outline_m:number[][];holes:GeneratedHole[];position_m:number[];depth_m:number}[];cylinder:{radius_m:number;length_m:number;radial_segments:number}|null;holes:GeneratedHole[];attachment_frames:{id:string;position_m:number[];rotation_rad:number[];source:string;hole_id:string|null}[];physical:ShapeSpec['physical'];limitations:string[]};
export type ShapePart={spec:ShapeSpec;geometry:ShapeGeometry};
export type ShapeLibrary={families:string[];parameter_constraints:Record<string,Record<string,{minimum:number;maximum:number}>>;minimum_wall_m:number;parts:ShapePart[];shape_spec_schema:unknown;source_sha256:Record<string,string>;ai_status:string;physical_scope:string;mobility_scope?:string};
export function shapeModel(part:ShapePart):THREE.Group{
 const {spec,geometry:g}=part;
 if(g.shape_id!==spec.id||g.body_id!==spec.body_id||g.geometry_revision!==spec.geometry_revision||g.dimensions_m.length!==3||!g.dimensions_m.every(v=>Number.isFinite(v)&&v>0)||g.sections.length>2||(!g.cylinder&&!g.sections.length))throw new Error('Invalid generated shape identity or dimensions');
 const root=new THREE.Group();root.name='shape:'+spec.id;root.userData={shapeId:spec.id,geometryRevision:spec.geometry_revision,objectId:spec.body_id,semantic:{body:spec.body_id,part:spec.id,joint:spec.joint_attachment?.joint_body_id}};
 const material=new THREE.MeshStandardMaterial({color:spec.family==='chassis'?'#537991':spec.family==='drone_arm'?'#596770':spec.family==='motor_pad'?'#c5a065':'#b9c7cd',metalness:.35,roughness:.42,side:THREE.DoubleSide});
 function add(geometry:THREE.BufferGeometry,name:string,position:number[]){const mesh=new THREE.Mesh(geometry,material);mesh.name=name;mesh.position.fromArray(position);mesh.userData={objectId:spec.body_id,shapeId:spec.id,geometryRevision:spec.geometry_revision};root.add(mesh);return mesh;}
 if(g.cylinder){const c=g.cylinder;if(!Number.isFinite(c.radius_m)||c.radius_m<=0||!Number.isFinite(c.length_m)||c.length_m<=0||c.radial_segments!==32)throw new Error('Invalid shaft geometry');add(new THREE.CylinderGeometry(c.radius_m,c.radius_m,c.length_m,32).rotateX(Math.PI/2),'solid-shaft',[0,0,0]);}
 for(const section of g.sections){
  if(section.outline_m.length<4||section.outline_m.length>64||section.outline_m.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v)))||!Number.isFinite(section.depth_m)||section.depth_m<=0||section.position_m.length!==3||section.position_m.some(v=>!Number.isFinite(v))||section.holes.length>8)throw new Error('Invalid bounded extrusion profile');
  const shape=new THREE.Shape(section.outline_m.map(p=>new THREE.Vector2(p[0],p[1])));
  for(const h of section.holes){if(h.center_m.some(v=>!Number.isFinite(v))||!Number.isFinite(h.radius_m)||h.radius_m<=0)throw new Error('Invalid hole contour');const path=new THREE.Path();path.absarc(h.center_m[0],h.center_m[1],h.radius_m,0,Math.PI*2,true);shape.holes.push(path);}
  const mesh=add(new THREE.ExtrudeGeometry(shape,{depth:section.depth_m,bevelEnabled:false,steps:1,curveSegments:16}),'shape-section:'+section.id,section.position_m);
  if(section.id==='tire')mesh.material=new THREE.MeshStandardMaterial({color:'#263039',roughness:.88,metalness:0});
 }
 // Axes annotate exact mounting centres; they neither fill holes nor collide.
 const radius=Math.max(.0015,Math.min(...g.dimensions_m)*.13);
 for(const frame of g.attachment_frames){
  const marker=new THREE.Group();marker.name='attachment:'+frame.id;marker.position.fromArray(frame.position_m);marker.rotation.set(...frame.rotation_rad as [number,number,number],'XYZ');marker.userData={shapeId:spec.id,frameId:frame.id,objectId:spec.body_id};
  const axes=new THREE.AxesHelper(radius*3);marker.add(axes);root.add(marker);
 }
 return root;
}

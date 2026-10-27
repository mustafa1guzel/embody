import {expect,it} from 'vitest';
import * as THREE from 'three';
import familiesRaw from '../test/shapebase_families.json?raw';
import raw from '../test/shapebase.json?raw';
import proposalRaw from '../test/shapebase_proposal.json?raw';
import {shapeModel,type ShapePart} from './shapeGeometry';
const original=JSON.parse(raw).shapebase.parts[0] as ShapePart,changed=JSON.parse(proposalRaw).validation.shapes.parts[0] as ShapePart;
it('renders actual through-holes from backend profiles, with stable part/frame identities',()=>{
 const model=shapeModel(original);model.updateMatrixWorld(true);const main=model.getObjectByName('shape-section:main') as THREE.Mesh;
 for(const hole of original.geometry.holes){const ray=new THREE.Raycaster(new THREE.Vector3(hole.center_m[0],hole.center_m[1],.1),new THREE.Vector3(0,0,-1));expect(ray.intersectObject(main)).toHaveLength(0);expect(model.getObjectByName('attachment:'+hole.id)?.userData.frameId).toBe(hole.id);}
 const ray=new THREE.Raycaster(new THREE.Vector3(0,0,.1),new THREE.Vector3(0,0,-1));expect(ray.intersectObject(main).length).toBeGreaterThan(0);
 expect(main.userData.objectId).toBe(original.spec.body_id);expect(model.userData.shapeId).toBe(original.spec.id);
});
it('backend parameter regeneration changes real vertex extents and mounting centres',()=>{
 const a=shapeModel(original),b=shapeModel(changed);
 const mesh=(g:THREE.Group)=>g.getObjectByName('shape-section:main') as THREE.Mesh;
 mesh(a).geometry.computeBoundingBox();mesh(b).geometry.computeBoundingBox();
 expect(mesh(a).geometry.boundingBox!.max.x*2).toBeCloseTo(.3,6);expect(mesh(b).geometry.boundingBox!.max.x*2).toBeCloseTo(.42,6);
 expect(a.getObjectByName('attachment:mount_b')!.position.x).toBeCloseTo(.096);expect(b.getObjectByName('attachment:mount_b')!.position.x).toBeCloseTo(.1344);
 expect(a.userData.shapeId).toBe(b.userData.shapeId);expect(b.userData.geometryRevision).toBe(a.userData.geometryRevision+1);
});
it('rejects malformed geometry or stale identity before claiming a render',()=>{
 const a=structuredClone(original);a.geometry.body_id='wrong';expect(()=>shapeModel(a)).toThrow('identity');
 const b=structuredClone(original);b.geometry.sections[0].outline_m[0][0]=NaN;expect(()=>shapeModel(b)).toThrow('profile');
});

it('all five backend-generated part families produce finite meshes with correct SI extents',()=>{
 for(const part of JSON.parse(familiesRaw) as ShapePart[]){const group=shapeModel(part);group.updateMatrixWorld(true);const bounds=new THREE.Box3();let count=0;group.traverse(o=>{if(o instanceof THREE.Mesh){count++;expect([...o.geometry.attributes.position.array].every(Number.isFinite)).toBe(true);bounds.expandByObject(o);}});expect(count).toBeGreaterThan(0);const size=bounds.getSize(new THREE.Vector3());expect(size.x).toBeCloseTo(part.geometry.dimensions_m[0],6);expect(size.y).toBeCloseTo(part.geometry.dimensions_m[1],6);expect(size.z).toBeCloseTo(part.geometry.dimensions_m[2],6);}
});

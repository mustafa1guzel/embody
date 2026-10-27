import {expect,it} from 'vitest';
import * as THREE from 'three';
import raw from '../test/mobility_families.json?raw';
import {shapeModel,type ShapePart} from './shapeGeometry';
const parts=JSON.parse(raw) as ShapePart[];
it('all six mobility meshes use generated SI profiles and finite bounds',()=>{
 for(const part of parts){const group=shapeModel(part),bounds=new THREE.Box3();group.updateMatrixWorld(true);group.traverse(o=>{if(o instanceof THREE.Mesh){expect([...o.geometry.attributes.position.array].every(Number.isFinite)).toBe(true);bounds.expandByObject(o);}});const size=bounds.getSize(new THREE.Vector3());for(let i=0;i<3;i++)expect(size.getComponent(i)).toBeCloseTo(part.geometry.dimensions_m[i],6);}
});
it('wheel has distinct tire/hub surfaces and a real through-bore',()=>{
 const p=parts.find(p=>p.spec.family==='wheel')!,g=shapeModel(p);g.updateMatrixWorld(true);
 const tire=g.getObjectByName('shape-section:tire') as THREE.Mesh,hub=g.getObjectByName('shape-section:hub') as THREE.Mesh;
 expect(tire.material).not.toBe(hub.material);expect((tire.material as THREE.MeshStandardMaterial).metalness).toBe(0);
 expect(new THREE.Raycaster(new THREE.Vector3(0,0,.2),new THREE.Vector3(0,0,-1)).intersectObjects([tire,hub])).toHaveLength(0);
 expect(new THREE.Raycaster(new THREE.Vector3(.04,0,.2),new THREE.Vector3(0,0,-1)).intersectObject(tire).length).toBeGreaterThan(0);
 expect(g.getObjectByName('attachment:axle')).toBeDefined();
});

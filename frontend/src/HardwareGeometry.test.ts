import {expect,it} from 'vitest';
import * as THREE from 'three';
import raw from '../test/hardware.json?raw';
import {endpointPosition} from './HardwareViewport';
import {applyDevicePoses} from './DeviceViewport';
const fixture=JSON.parse(raw);
it('updates real wire endpoints under translation and Euler XYZ rotation',()=>{
 const a=structuredClone(fixture.bootstrap.template),e={component:'board',pin:'IO18'},before=endpointPosition(a,fixture.bootstrap.catalog,e);
 a.components[0].position_m[0]+=.03;
 expect(endpointPosition(a,fixture.bootstrap.catalog,e)[0]-before[0]).toBeCloseTo(.03,12);
 a.components[0].rotation_rad=[.2,.4,.7];
 const expected=new THREE.Vector3(...fixture.bootstrap.catalog[a.components[0].part].pins[2].position_m).applyEuler(new THREE.Euler(.2,.4,.7)).add(new THREE.Vector3(...a.components[0].position_m));
 expect(endpointPosition(a,fixture.bootstrap.catalog,e)).toEqual(expected.toArray());
 expect(a.wires).toEqual(fixture.bootstrap.template.wires);
});
it('reconstructs measured device states directly on actual Three meshes',()=>{
 const meshes=fixture.run.scene.geoms.map(()=>new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshBasicMaterial()));
 for(const s of fixture.run.samples){applyDevicePoses(meshes,s);meshes.forEach((m:THREE.Mesh,i:number)=>{expect(m.position.toArray()).toEqual(s.geom_poses[i].position);const [w,x,y,z]=s.geom_poses[i].quaternion_wxyz;expect(m.quaternion.toArray()).toEqual([x,y,z,w]);});}
 expect(()=>applyDevicePoses(meshes,{...fixture.run.samples[0],geom_poses:[]})).toThrow('missing');
 meshes.forEach((m:THREE.Mesh)=>{m.geometry.dispose();(m.material as THREE.Material).dispose();});
});

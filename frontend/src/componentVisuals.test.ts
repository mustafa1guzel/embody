import {expect,it} from 'vitest';
import * as THREE from 'three';
import raw from '../test/hardware.json?raw';
import {diagnosticNets,signalCategory} from './circuitPresentation';
import {visualSpec,validateVisualSpec,componentModel,endpointPosition,wireCurve} from './componentVisuals';
import type {Part,Assembly} from './hardwareTypes';
const fixture=JSON.parse(raw),catalog=fixture.bootstrap.catalog as Record<string,Part>;
it('maps every supported catalog pin exactly once, with bounded nonoverlapping local targets',()=>{
 for(const part of Object.values(catalog)){
  const spec=visualSpec(part);expect(spec.fallback).toBe(false);expect(spec.catalogId).toBe(part.id);
  for(const pin of part.pins){const anchor=spec.pins.find(p=>p.id===pin.id)!;expect(anchor.position).toEqual(pin.position_m);for(const other of spec.pins.filter(p=>p.id!==pin.id))expect(anchor.hitRadius+other.hitRadius).toBeLessThan(new THREE.Vector3(...anchor.position).distanceTo(new THREE.Vector3(...other.position)));}
  const missing=structuredClone(spec);missing.pins.pop();expect(()=>validateVisualSpec(missing,part)).toThrow('Missing');
  const duplicate=structuredClone(spec);duplicate.pins[1]=duplicate.pins[0];expect(()=>validateVisualSpec(duplicate,part)).toThrow('duplicate');
  const moved=structuredClone(spec);moved.pins[0].position[0]+=.001;expect(()=>validateVisualSpec(moved,part)).toThrow('authoritative');
 }
});
it('builds recognizable local mesh structures and an explicit fallback without inventing graph pins',()=>{
 const before=JSON.stringify(catalog);
 for(const part of Object.values(catalog)){const group=componentModel(part);expect(group.children.filter(c=>c.userData.pin&&!c.userData.hitTarget)).toHaveLength(part.pins.length);group.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();if(m.material)(m.material as THREE.Material).dispose();});}
 expect(visualSpec(catalog.hcsr04_sen15569).meshes.filter(m=>m.name==='metal-transducer')).toHaveLength(2);
 expect(visualSpec(catalog.esp32_devkitc_v4_wroom32).meshes.map(m=>m.name)).toContain('usb-connector');
 expect(visualSpec(catalog.towerpro_sg90_digital).meshes.map(m=>m.name)).toContain('servo-horn');
 const unsupported={...catalog.connector_2,id:'future_catalog_part',kind:'unsupported'};expect(visualSpec(unsupported).fallback).toBe(true);expect(visualSpec(unsupported).pins.map(p=>p.id)).toEqual(unsupported.pins.map(p=>p.id));
 expect(JSON.stringify(catalog)).toBe(before);
});
it('keeps both curved wire endpoints on exact rotated catalog anchors without changing the graph',()=>{
 const a=structuredClone(fixture.bootstrap.template) as Assembly,before=JSON.stringify(a.wires),wire=a.wires[0];
 for(const angle of [0,.3,-1.7]){a.components[0].rotation_rad=[angle,.2,.8];a.components[0].position_m=[.07,-.1,.02];const p=endpointPosition(a,catalog,wire.a),q=endpointPosition(a,catalog,wire.b),curve=wireCurve(p,q);expect(curve.getPoint(0).toArray()).toEqual(p);curve.getPoint(1).toArray().forEach((v,i)=>expect(v).toBeCloseTo(q[i],14));}
 expect(JSON.stringify(a.wires)).toBe(before);expect(()=>endpointPosition(a,catalog,{component:'absent',pin:'CC'})).toThrow('Absent');
});

it('uses diagnostic references for error nets and keeps UNKNOWN separate from errors',()=>{
 const a=fixture.bootstrap.template,w=a.wires[0];expect(diagnosticNets(a,{...fixture.diagnostics,diagnostics:[{code:'UNSPECIFIED',severity:'UNKNOWN',message:'unknown',references:[w.net]}]}).size).toBe(0);
 expect(diagnosticNets(a,{...fixture.diagnostics,diagnostics:[{code:'VOLTAGE_INCOMPATIBLE',severity:'ERROR',message:'bad',references:[[w.a.component,w.a.pin]]}]}).has(w.net)).toBe(true);expect(signalCategory(a,catalog,w)).toBe('Power');
});

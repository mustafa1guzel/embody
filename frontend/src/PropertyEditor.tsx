import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {readDraft,writeDraft,clearDraft} from './localDraft';
import type {Project,WorldObject} from './engineeringTypes';
import type {ShapeSpec} from './shapeGeometry';
export type EditField={key:string;label:string;value:number;min?:number;max?:number};
export function editableFields(project:Project,body:WorldObject,shape?:ShapeSpec):EditField[]{
 if(project.creation||body.id==='floor')return [];
 if(shape)return Object.entries(shape.parameters).map(([key,value])=>({key:'shape:'+key,label:key.replace(/_m$/,'').replaceAll('_',' ')+' (m)',value}));
 const fields:EditField[]=[{key:'mass',label:'Mass (kg)',value:body.mass_kg,min:0,max:100}];
 const constrained=project.shape_specs?.some(s=>s.mounted_bodies.some(m=>m.body_id===body.id)||s.parent_body_id===body.id);
 if(!constrained){body.dimensions_m.forEach((v,i)=>fields.push({key:'dimension:'+i,label:['Width (m)','Depth (m)','Height (m)'][i],value:v,min:.005,max:5}));body.position_m.forEach((v,i)=>fields.push({key:'position:'+i,label:'Local '+['X','Y','Z'][i]+' (m)',value:v,min:-10,max:10}));body.rotation_rad.forEach((v,i)=>fields.push({key:'rotation:'+i,label:'Local rotation '+['X','Y','Z'][i]+' (rad)',value:v,min:-2*Math.PI,max:2*Math.PI}));}
 return fields;
}
export function propertyOperation(body:WorldObject,shape:ShapeSpec|undefined,key:string,value:number){
 if(!Number.isFinite(value))throw new Error('Enter a finite number.');
 if(key.startsWith('shape:')&&shape&&Object.hasOwn(shape.parameters,key.slice(6)))return {kind:'update_shape_parameter',target:shape.id,parameter:key.slice(6),value};
 if(key==='mass')return {kind:'set_mass',target:body.id,mass_kg:value};
 const [type,n]=key.split(':'),i=Number(n);if(!Number.isInteger(i)||i<0||i>2)throw new Error('Unsupported property.');
 const source=type==='dimension'?body.dimensions_m:type==='position'?body.position_m:type==='rotation'?body.rotation_rad:null;if(!source)throw new Error('Unsupported property.');
 const values=[...source];values[i]=value;return type==='dimension'?{kind:'set_geometry',target:body.id,dimensions_m:values}:type==='position'?{kind:'move_object',target:body.id,position_m:values}:{kind:'rotate_object',target:body.id,rotation_rad:values};
}
export default function PropertyEditor({project,sha,body,shape,enabled,onProposal}:{project:Project;sha:string;body:WorldObject;shape?:ShapeSpec;enabled:boolean;onProposal:(p:any)=>void}){
 const fields=editableFields(project,body,shape),storageKey='property:'+sha+':'+body.id;
 const saved=readDraft<{key:string;value:string}>(storageKey),valid=saved&&fields.some(f=>f.key===saved.key)&&typeof saved.value==='string'&&saved.value.length<100;
 const [key,setKey]=useState(valid?saved.key:fields[0]?.key||''),[value,setValue]=useState(valid?saved.value:String(fields[0]?.value??'')),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const alive=useRef(true),pending=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 const field=fields.find(f=>f.key===key);const changed=field&&value!==String(field.value);
 useEffect(()=>{if(enabled&&field){if(changed)writeDraft(storageKey,{key,value});else clearDraft(storageKey);}},[storageKey,key,value,enabled,changed]);
 if(!enabled)return <p className="studio-readonly">Read-only representation. Return to the current project to edit; historical evidence and saved simulations cannot be changed.</p>;
 if(!field)return <p className="studio-readonly">This object's geometry or device binding is protected. Use its existing validated editor for supported changes.</p>;
 return <form className="property-editor" aria-label="Typed property editor" noValidate onSubmit={e=>{e.preventDefault();if(pending.current)return;if(value.trim()===''){setError('Enter a number.');return;}pending.current=true;setBusy(true);setError('');void (async()=>{try{const operations=[propertyOperation(body,shape,key,Number(value))];const proposal=await api<any>('engineering/propose',{expected_sha256:sha,expected_revision:project.revision,operations,explanation:'Explicit local property edit for review. No model authorship, application or dynamics.'});if(alive.current){clearDraft(storageKey);onProposal(proposal);}}catch(e){if(alive.current)setError(String((e as Error).message||e));}finally{pending.current=false;if(alive.current)setBusy(false);}})();}}>

  <header><h4>Edit a property</h4><span>Review required</span></header>
  <label>Property<select aria-label="Editable property" value={key} disabled={busy} onChange={e=>{setKey(e.target.value);setValue(String(fields.find(f=>f.key===e.target.value)!.value));setError('');}}>{fields.map(f=><option key={f.key} value={f.key}>{f.label}</option>)}</select></label>
  <label>{field.label}<input aria-label="Property value" type="number" step="any" min={field.min} max={field.max} value={value} disabled={busy} onChange={e=>{setValue(e.target.value);setError('');}}/></label>
  <p className="note">Current: {field.value}. {shape?'Dimensions regenerate through SHAPEBASE.':'Placement is in the parent-local frame.'} A draft does not change the canvas or project.</p>
  {error&&<div role="alert" className="studio-validation"><strong>Change rejected</strong><p>This value could not be validated against the part’s engineering constraints.</p><small>Project unchanged. Correct the value or cancel.</small><details><summary>Exact validation message</summary><p>{error}</p></details></div>}
  <div className="studio-actions"><button type="button" disabled={busy||!changed} onClick={()=>{setValue(String(field.value));setError('');}}>Cancel edit</button><button className="studio-primary" disabled={busy||!changed} type="submit">{busy?'Validating…':'Review change'}</button></div>
 </form>;
}

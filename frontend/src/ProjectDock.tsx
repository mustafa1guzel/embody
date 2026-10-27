import {ChevronDown,FileCode2,Folder,Box,Layers,Settings2} from 'lucide-react';
import type {Bootstrap,Scene,SceneObject,Sample} from './types';

export type DockView='files'|'scene'|'settings';
export function ActivityRail({view,onView}:{view:DockView;onView:(view:DockView)=>void}){
 return <nav className="activity-rail" aria-label="Workbench tools">
  <button aria-label="Project Files" title="Project Files" aria-pressed={view==='files'} onClick={()=>onView('files')}><Folder size={19}/></button>
  <button aria-label="Scene" title="Scene hierarchy" aria-pressed={view==='scene'} onClick={()=>onView('scene')}><Layers size={19}/></button>
  <span className="spacer"/>
  <button aria-label="Workspace settings" title="Workspace settings" aria-pressed={view==='settings'} onClick={()=>onView('settings')}><Settings2 size={18}/></button>
 </nav>;
}
export function ProjectDock({view,files,active,dirty,scene,selection,onSelect,onFile,onReset,draftObject,onDraftObject}:{view:DockView;files:Bootstrap['files'];active:string;dirty:string[];scene?:Scene;selection:string;onSelect:(id:string)=>void;onFile:(path:string)=>void;onReset:()=>void;draftObject:string;onDraftObject:(value:string)=>void}){
 const groups=[...new Set(files.map(f=>f.path.split('/')[0]))];
 return <aside className="explorer"><div className="panel-title"><strong>{view==='files'?'Project':view==='scene'?'Scene hierarchy':'Workspace'}</strong><span className="spacer"/><small>{view==='scene'?'MuJoCo':'rail-carriage'}</small></div>
  <div className="explorer-scroll">{view==='files'?<><div className="tree-root"><ChevronDown size={12}/> rail-carriage</div>{groups.map(group=><details className="file-group" key={group} open><summary><Folder size={13}/>{group}<small>{files.filter(f=>f.path.startsWith(group+'/')).length}</small></summary>{files.filter(f=>f.path.startsWith(group+'/')).map(f=><button key={f.path} aria-label={f.path} title={f.path} className={'file-entry '+(active===f.path?'selected':'')} onClick={()=>onFile(f.path)}><FileCode2 size={13}/><span>{f.path.slice(group.length+1)}</span>{dirty.includes(f.path)&&<i className="unsaved"/>}{f.historical&&<small title="Historical evidence">R</small>}</button>)}</details>)}</>:view==='scene'?<>
   <div className="tree-root"><Box size={13}/> Single-axis carriage</div>
   {scene?(['body','joint','actuator','geom'] as const).map(kind=><details className="scene-group" open key={kind}><summary>{({body:'Bodies',joint:'Joints',actuator:'Actuators',geom:'Geometry'})[kind]}</summary><div className="scene-tree">{[...scene.bodies,...scene.joints,...scene.actuators,...scene.geoms].filter(o=>o.kind===kind).map(o=><button key={o.id} className={selection===o.id?'selected':''} onClick={()=>onSelect(o.id)}><span className="tree-kind">{kind==='geom'?'G':kind==='body'?'B':kind==='joint'?'J':'A'}</span><span>{o.name}</span><small>{o.kind}</small></button>)}</div></details>):<p className="note dock-note">Scene data is loading.</p>}
   <details className="draft-object"><summary>Add object note</summary><label>Local object note<input value={draftObject} onChange={e=>onDraftObject(e.target.value)} placeholder="Name / intended geometry"/></label><p className="note">Draft only. No physical geometry or configuration is changed.</p></details>
  </>:<div className="workspace-settings"><h3>Layout</h3><p className="note">Drag separators or use arrow keys. Cmd/Ctrl+1, 2, 3 switches workspace modes.</p><button onClick={onReset}><Settings2 size={14}/>Reset layout</button><h3>Execution</h3><p className="note">Opening the workspace costs $0. Paid generation, VM verification and application require separate approval.</p></div>}</div>
 </aside>;
}
export function Inspector({object,scene,sample}:{object?:SceneObject;scene?:Scene;sample?:Sample}){
 if(!object||!scene||!sample)return <div className="inspector-empty"><Box size={24}/><h3>No object selected</h3><p className="note">Select geometry in the scene or hierarchy.</p></div>;
 let body=object.kind==='body'?Number(object.id.split(':')[1]):object.body;
 let moving=!!object.moving;
 while(typeof body==='number'&&body>0){moving ||= scene.joints.some(j=>j.body===body);body=scene.bodies.find(b=>b.id==='body:'+body)?.parent;}
 const position=object.position?.map((v,i)=>v+(moving?scene.slide_axis_world[i]*(sample.position-scene.reference_position):0));
 const entries:[string,unknown][]=[['Identity',object.id],['Type',object.kind],['Position (m)',position],['Orientation (wxyz)',object.quaternion_wxyz],['Mass (kg)',object.mass_kg],['Half-size / radius (m)',object.size],['Axis',object.axis],['Joint limited',object.limited],['Joint range',object.range],['Force limits (N)',object.force_range_n],['Control range',object.control_range],['Collision enabled',object.collision]];
 const format=(value:unknown)=>Array.isArray(value)?value.map(v=>typeof v==='number'?Number(v.toFixed(5)):String(v)).join('  '):String(value);
 return <section className="inspector"><div className="inspector-heading"><Box size={17}/><div><strong>{object.name}</strong><small>SELECTION / {object.name}</small></div></div><dl>{entries.filter(([,value])=>value!==undefined&&value!==null).map(([name,value])=><div key={name}><dt>{name}</dt><dd>{format(value)}</dd></div>)}</dl><details><summary>Exact compiled properties</summary><pre>{JSON.stringify(object,null,2)}</pre></details></section>;
}

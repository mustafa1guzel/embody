import {Suspense,lazy,useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Box,Code2,FolderTree,PanelLeftClose,PanelRightClose,Maximize2,Minimize2,Play,Pause,SkipBack,SkipForward,StepBack,StepForward,RotateCcw,ChevronRight,FileCode2,Layers,Plus,Activity,Terminal,ShieldCheck,GitCompareArrows,Settings2} from 'lucide-react';
import {api,job,setToken} from './api';
import {usePlayback} from './playback';
import type {Bootstrap,Experiment,FileData,Mode,Proposal,RecordedAgent,SceneObject,Variant} from './types';
import {labels} from './types';
import AgentPanel from './AgentPanel';
import PatchReview from './PatchReview';
import {Telemetry} from './Telemetry';
import type {CameraMemory} from './Viewport';
import {ActivityRail,ProjectDock,Inspector} from './ProjectDock';
import type {DockView} from './ProjectDock';
import {TimelineTracks} from './TimelineTracks';
import PhysicsPanel from './PhysicsPanel';
import ArmWorkspace from './ArmWorkspace';
const Editor=lazy(()=>import('./Editor'));
const Viewport=lazy(()=>import('./Viewport'));
const EngineeringWorkspace=lazy(()=>import('./UnifiedWorkspace'));
const RobustnessPanel=lazy(()=>import('./RobustnessPanel'));
const DEFAULT_FILE='robot/controller.py';
const dockTabs=['Timeline','Telemetry','Physics','Console','Verification','Agent Activity','Problems','Output','Tests','Diagnostics'];

function loadLayout(){try{const v=JSON.parse(localStorage.getItem('embody-layout')||'{}');return {left:typeof v.left==='number'?Math.min(380,Math.max(160,v.left)):232,right:typeof v.right==='number'?Math.min(540,Math.max(260,v.right)):340,bottom:typeof v.bottom==='number'?Math.min(460,Math.max(150,v.bottom)):200};}catch{return {left:232,right:340,bottom:200};}}
function Resize({label,direction,value,onChange}:{label:string;direction:'left'|'right'|'bottom';value:number;onChange:(v:number)=>void}){
 const vertical=direction!=='bottom';const drag=useRef<{start:number;value:number}|null>(null);
 return <div className={'resize-handle '+(vertical?'vertical':'horizontal')} role="separator" aria-label={label} aria-orientation={vertical?'vertical':'horizontal'} aria-valuenow={Math.round(value)} aria-valuemin={vertical?160:150} aria-valuemax={vertical?540:460} tabIndex={0}
  onKeyDown={event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();const sign=event.key==='ArrowLeft'||event.key==='ArrowUp'?-1:1;onChange(value+sign*16*(direction==='left'?1:-1));}}}
  onPointerDown={e=>{drag.current={start:vertical?e.clientX:e.clientY,value};e.currentTarget.setPointerCapture(e.pointerId);}}
  onPointerMove={e=>{if(drag.current)onChange(drag.current.value+((vertical?e.clientX:e.clientY)-drag.current.start)*(direction==='left'?1:-1));}}
  onPointerUp={()=>{drag.current=null;}} onLostPointerCapture={()=>{drag.current=null;}}/>;
}

export default function App(){
 const [extended,setExtended]=useState<'hardware'|'world'|'robustness'|null>('hardware'),[hardwareOpened,setHardwareOpened]=useState(true);
 const [theme,setTheme]=useState(()=>localStorage.getItem('embody-theme')||'light');
 useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('embody-theme',theme);window.dispatchEvent(new Event('embody-theme-change'));},[theme]);
 const [family,setFamily]=useState<'rail'|'arm'>('rail');
 const [bootstrap,setBootstrap]=useState<Bootstrap|null>(null),[experiment,setExperiment]=useState<Experiment|null>(null),[recorded,setRecorded]=useState<RecordedAgent|null>(null);
 const [scenario,setScenario]=useState('A'),[variant,setVariant]=useState<Variant>('original'),[proposalVariant,setProposalVariant]=useState<'attempt_1'|'attempt_2'>('attempt_2'),[proposal,setProposal]=useState<Proposal|null>(null);
 const [mode,setMode]=useState<Mode>('studio'),[priorMode,setPriorMode]=useState<Mode>('studio'),[files,setFiles]=useState<Record<string,FileData>>({}),[tabs,setTabs]=useState<string[]>([DEFAULT_FILE]),[active,setActive]=useState(DEFAULT_FILE),[drafts,setDrafts]=useState<Record<string,string>>({}),[diff,setDiff]=useState(false);
 const [index,setIndex]=useState(0),[selection,setSelection]=useState('body:2'),[dock,setDock]=useState('Timeline'),[compare,setCompare]=useState(false),[showLeft,setShowLeft]=useState(true),[showAgent,setShowAgent]=useState(true),[showDock,setShowDock]=useState(true),[maximized,setMaximized]=useState(false),[layout,setLayout]=useState(loadLayout),[reviewDiff,setReviewDiff]=useState<{original:string;modified:string}|undefined>();
 const [error,setError]=useState(''),[log,setLog]=useState<string[]>(['IDE initialized. No model or simulator execution requested.']),[prerequisites,setPrerequisites]=useState<any>(null),[draftObject,setDraftObject]=useState(''),[resumeId,setResumeId]=useState('');
 const [dockView,setDockView]=useState<DockView>('files'),[rightTab,setRightTab]=useState<'agent'|'inspector'>('agent');
 const camera=useRef<CameraMemory|null>(null),cache=useRef(new Map<string,Experiment>()),requestId=useRef(0);
 const samples=experiment?.variants[variant].samples||[];
 const playback=usePlayback(samples,index,setIndex);
 const reportError=useCallback((message:string)=>{setError(message);setLog(l=>[...l,'BLOCKED: '+message]);},[]);
 const openFile=useCallback(async(path:string)=>{setActive(path);setTabs(v=>v.includes(path)?v:[...v,path]);setDiff(false);try{const file=await api<FileData>('file?path='+encodeURIComponent(path));setFiles(f=>({...f,[path]:file}));}catch(e){reportError(String(e));}},[reportError]);
 useEffect(()=>{let alive=true;Promise.all([api<Bootstrap>('bootstrap'),api<RecordedAgent>('agent/recorded')]).then(([b,r])=>{if(alive){setToken(b.csrf_token);setBootstrap(b);setRecorded(r);}}).catch(e=>{if(alive)reportError(String(e));});return()=>{alive=false;};},[reportError]);
 useEffect(()=>{void openFile(DEFAULT_FILE);},[openFile]);
 useEffect(()=>{let alive=true;setProposal(null);api<Proposal>('proposal?variant='+proposalVariant).then(v=>{if(alive)setProposal(v);}).catch(e=>{if(alive)reportError(String(e));});return()=>{alive=false;};},[proposalVariant,reportError]);
 useEffect(()=>{
  const id=++requestId.current;playback.pause();setExperiment(null);setIndex(0);
  const existing=cache.current.get(scenario);if(existing){setExperiment(existing);return;}
  api<Experiment>('experiment?scenario='+scenario).then(e=>{cache.current.set(scenario,e);if(requestId.current===id)setExperiment(e);}).catch(e=>{if(requestId.current===id)reportError(String(e));});
  // Scenario changes deliberately pause playback and reset to measured sample 0.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[scenario,reportError]);
 useEffect(()=>{localStorage.setItem('embody-layout',JSON.stringify(layout));},[layout]);
 const changeMode=useCallback((next:Mode)=>{setExtended(null);if(next==='agent'&&mode!=='agent')setPriorMode(mode);setMode(next);setMaximized(false);},[mode]);
 useEffect(()=>{if(extended)playback.pause();},[extended]);
 const focusAgent=useCallback(()=>changeMode(mode==='agent'?priorMode:'agent'),[changeMode,mode,priorMode]);
 useEffect(()=>{const handler=(event:KeyboardEvent)=>{
  if(family==='arm'||extended)return; // Never advance a hidden replay.
  const target=event.target as HTMLElement;const editing=['INPUT','TEXTAREA','SELECT'].includes(target.tagName)||target.isContentEditable||!!target.closest('.monaco-editor');
  if((event.metaKey||event.ctrlKey)&&['1','2','3'].includes(event.key)){event.preventDefault();changeMode(({1:'studio',2:'code',3:'agent'} as Record<string,Mode>)[event.key]);}
  else if(!editing&&event.code==='Space'&&samples.length){event.preventDefault();playback.toggle();}
  else if(!editing&&event.key==='ArrowRight'&&samples.length){event.preventDefault();playback.seek(index+1);}
  else if(!editing&&event.key==='ArrowLeft'&&samples.length){event.preventDefault();playback.seek(index-1);}
  else if(event.key==='Escape')setMaximized(false);
 };window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[changeMode,index,playback,samples.length,family,extended]);
 function resize(direction:'left'|'right'|'bottom',value:number){setLayout(l=>{const room=window.innerWidth-292-(direction==='left'?(showAgent?l.right:0):(showLeft?l.left:0));return {...l,[direction]:Math.min(direction==='bottom'?460:Math.max(direction==='left'?160:260,Math.min(direction==='left'?380:540,room)),Math.max(direction==='bottom'?150:direction==='left'?160:260,value))};});}
 function review(id:string){setResumeId(id);setDock('Verification');setShowDock(true);if(mode==='agent')changeMode('code');setLog(l=>[...l,'Review journal: '+id]);}
 function resetLayout(){setLayout({left:232,right:340,bottom:200});setShowLeft(true);setShowAgent(true);setShowDock(true);setMaximized(false);}
 function selectObject(id:string){setSelection(id);setRightTab('inspector');setShowAgent(true);}
 function openProposal(next:'attempt_1'|'attempt_2',showDiff:boolean){if(next!==proposalVariant)setProposal(null);setProposalVariant(next);setResumeId('');setReviewDiff(undefined);setDock('Verification');setShowDock(true);if(showDiff){setActive(DEFAULT_FILE);setTabs(t=>t.includes(DEFAULT_FILE)?t:[...t,DEFAULT_FILE]);setDiff(true);changeMode('code');}else if(mode==='agent')changeMode('studio');}
 const current=samples[index],file=files[active],trajectory=experiment?.variants[variant];
 const selected=experiment&&[...experiment.scene.bodies,...experiment.scene.geoms,...experiment.scene.joints,...experiment.scene.actuators].find(o=>o.id===selection);
 const visibleLeft=showLeft&&mode!=='agent'&&!maximized,visibleAgent=(showAgent||mode==='agent')&&!maximized;
 const editorDiff=useMemo(()=>diff&&proposal?(reviewDiff||{original:files[DEFAULT_FILE]?.content||'',modified:proposal.source}):undefined,[diff,proposal,reviewDiff,files[DEFAULT_FILE]?.content]);
 const style={'--left':visibleLeft?`${layout.left}px`:'0px','--right':visibleAgent&&mode!=='agent'?`${layout.right}px`:'0px','--bottom':showDock&&!maximized?`${layout.bottom}px`:'0px'} as React.CSSProperties;
 if(!bootstrap||!recorded)return <main className="startup"><div className="brand">E<span>EMBODY</span></div><p>{error?'Workspace BLOCKED':'Loading verified project evidence…'}</p>{error&&<p role="alert">{error}</p>}<p>No model requests are made on startup.</p></main>;
 if(family==='arm')return <ArmWorkspace mode={mode} onMode={changeMode} onRail={()=>setFamily('rail')}/>;
 const workspaceNav=<nav aria-label="Workspace mode">{(['studio','code','agent'] as Mode[]).filter(m=>!extended||m==='studio').map(m=><button key={m} aria-pressed={!extended&&mode===m} title={`⌘${m==='studio'?1:m==='code'?2:3}`} onClick={()=>changeMode(m)}>{m==='studio'?<Box size={14}/>:m==='code'?<Code2 size={14}/>:<Activity size={14}/>}<span>{m==='agent'?'Agent focus':m[0].toUpperCase()+m.slice(1)}</span></button>)}<button aria-pressed={extended==='hardware'} onClick={()=>{setHardwareOpened(true);setExtended('hardware');}}>Build</button><button aria-pressed={extended==='robustness'} onClick={()=>setExtended('robustness')}>Robustness</button></nav>;
 return <div className={'ide mode-'+mode+(maximized?' maximized':'')+(extended?' extended-mode':'')} style={style}>
  <header className={'topbar'+(extended==='hardware'||extended==='world'?' studio-shell-topbar':'')}><div className="brand"><span className="brand-symbol">E</span><strong>EMBODY</strong><span className="project-name">/ {extended==='hardware'||extended==='world'?'engineering-project':extended==='robustness'?'robustness':'rail-carriage'}</span></div>
   {(extended==='hardware'||extended==='world')?<details className="studio-workspaces-menu"><summary>Advanced workspaces</summary><div className="studio-workspace-options">   {workspaceNav}
<button onClick={()=>setFamily('arm')}>Planar arm</button></div></details>:<>   {workspaceNav}
<button onClick={()=>setFamily('arm')}>Planar arm</button></>}
   <span className="spacer"/><button aria-label="Toggle color theme" onClick={()=>setTheme(t=>t==='light'?'dark':'light')}>{theme==='light'?'◐':'☀'}</button>
   <label className="scenario-select">Scenario<select aria-label="Scenario" value={scenario} onChange={e=>setScenario(e.target.value)}>{['A','B','C'].map(s=><option key={s}>{s}</option>)}</select></label>
   <select className="controller-select" aria-label="Playback controller" value={variant} onChange={e=>{playback.pause();setVariant(e.target.value as Variant);}}>{Object.entries(labels).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>
   <button aria-label="Toggle explorer" onClick={()=>setShowLeft(v=>!v)}><PanelLeftClose size={14}/></button><button aria-label="Toggle agent" onClick={()=>setShowAgent(v=>!v)}><PanelRightClose size={14}/></button>
   <button title="Reset layout" aria-label="Reset layout" onClick={resetLayout}><Settings2 size={15}/></button>
  </header>
  {error&&<div className="error-banner" role="alert"><strong>BLOCKED</strong> {error}<button onClick={()=>setError('')}>Dismiss</button></div>}
  {hardwareOpened&&<div className="extended-workspace" style={{display:extended==='hardware'||extended==='world'?'flex':'none'}}><Suspense fallback={<p>Loading unified engineering workspace…</p>}><EngineeringWorkspace visible={extended==='hardware'||extended==='world'}/></Suspense></div>}
  {extended==='robustness'&&<div className="extended-workspace"><Suspense fallback={<p>Loading robustness contracts…</p>}><RobustnessPanel/></Suspense></div>}
  <div className="workspace" style={{display:extended?'none':undefined}}>
   {mode!=='agent'&&!maximized&&<ActivityRail view={dockView} onView={view=>{setDockView(view);setShowLeft(true);}}/>}
   {visibleLeft&&<><ProjectDock view={dockView} files={bootstrap.files} active={active} dirty={Object.keys(drafts).filter(p=>drafts[p]!==files[p]?.content)} scene={experiment?.scene} selection={selection} onSelect={selectObject} onFile={path=>{void openFile(path);changeMode('code');}} onReset={resetLayout} draftObject={draftObject} onDraftObject={setDraftObject}/><Resize label="Resize explorer" direction="left" value={layout.left} onChange={v=>resize('left',v)}/></>}
   <main className="main-workspace" hidden={mode==='agent'}>
    <div className="main-content"><div className="content-title"><span>{mode==='studio'?'Single-axis carriage':diff?'Original ↔ proposal':'Project source'}</span><span className="spacer"/><button aria-label="Maximize or restore main panel" onClick={()=>setMaximized(v=>!v)}>{maximized?<Minimize2 size={13}/>:<Maximize2 size={13}/>}</button></div>
     <div className="studio-content" hidden={mode!=='studio'}>{!extended&&experiment&&current?<Suspense fallback={<p>Loading 3D renderer…</p>}><Viewport scene={experiment.scene} sample={current} selection={selection} onSelect={selectObject} visible={mode==='studio'} cameraMemory={camera} scenario={scenario} minimumClearance={experiment.context.minimum_clearance_m}/></Suspense>:<div className="empty-state">Loading actual scenario geometry and measured states…</div>}
      {experiment&&current&&<><div className="measurement-strip"><div><small>Position</small><strong data-testid="scene-position">{current.position.toFixed(4)}<em>m</em></strong></div><div><small>Velocity</small><strong>{current.velocity.toFixed(4)}<em>m/s</em></strong></div><div><small>Surface gap</small><strong className={current.wall_clearance<experiment.context.minimum_clearance_m?'danger':''}>{current.wall_clearance.toFixed(4)}<em>m</em></strong></div><div><small>Force</small><strong>{current.generalized_actuator_force.toFixed(2)}<em>N</em></strong></div><div><small>Contact</small><strong className={current.wall_collision?'danger':''}>{current.wall_collision?'DETECTED':'NONE'}</strong></div></div>
      <div className="physical-context"><span>{experiment.context.mass_kg} kg</span><span>±{experiment.context.braking_force_n} N</span><span>v₀ {experiment.context.initial_velocity_ms} m/s</span><span>Wall center {experiment.context.wall_center_x_m} m · face {experiment.context.wall_near_x} m</span><span>Gap ≥ {experiment.context.minimum_clearance_m} m · |v final| &lt; {experiment.context.max_final_speed_ms} m/s · ≤ {experiment.context.completion_deadline_s} s</span></div></>}
     </div>
     <div className="code-content" hidden={mode!=='code'}><div className="file-tabs">{tabs.map(path=><button key={path} aria-pressed={active===path} title={path} onClick={()=>{setActive(path);setDiff(false);}}><FileCode2 size={12}/>{path.split('/').at(-1)}{drafts[path]!==undefined&&drafts[path]!==files[path]?.content&&<i className="unsaved"/>}<span role="button" tabIndex={0} aria-label={'Close '+path} onClick={e=>{e.stopPropagation();const next=tabs.filter(p=>p!==path);setTabs(next);if(active===path)setActive(next[0]||'');}} onKeyDown={e=>{if(e.key==='Enter'){const next=tabs.filter(p=>p!==path);setTabs(next);setActive(next[0]||'');}}}>×</span></button>)}</div>
      <div className="editor-status">{file?<><span>{file.historical?'HISTORICAL · READ ONLY':drafts[active]!==undefined&&drafts[active]!==file.content?'UNSAVED LOCAL DRAFT · UNVALIDATED':'ORIGINAL PROJECT SOURCE'}</span><code>{file.sha256.slice(0,16)}</code><span className="spacer"/>{active===DEFAULT_FILE&&<button onClick={()=>{setReviewDiff(undefined);setDiff(v=>!v);}}><GitCompareArrows size={12}/>{diff?'Back to draft':'Compare GPT proposal'}</button>}</>:<span>No file selected</span>}</div>
      {!extended&&mode==='code'&&file&&diff&&!proposal?<div className="empty-state">Loading exact proposal diff…</div>:!extended&&mode==='code'&&file&&<Suspense fallback={<div className="empty-state">Loading local Monaco editor…</div>}><Editor file={file} draft={drafts[active]??file.content} onChange={value=>setDrafts(d=>({...d,[active]:value}))} diff={editorDiff}/></Suspense>}
      {active===DEFAULT_FILE&&drafts[active]!==undefined&&drafts[active]!==file?.content&&<div className="draft-actions"><span>Editing is local only; source policy and physics have not run.</span><button onClick={async()=>{try{const result=await job<{review_id:string}>('review/create',{source:drafts[active],explanation:'Manual Monaco draft submitted for explicit review; not AI generated',expected_original_sha256:file.sha256});review(result.review_id);}catch(e){reportError(String(e));}}}>Submit draft for source review</button></div>}
     </div>
    </div>
    {!maximized&&<><Resize label="Resize engineering dock" direction="bottom" value={layout.bottom} onChange={v=>resize('bottom',v)}/><section className="dock" style={{height:showDock?layout.bottom:33}}><div className="dock-tabs" role="tablist" aria-label="Engineering panels">{dockTabs.map(tab=><button key={tab} role="tab" aria-selected={dock===tab} onClick={()=>{setDock(tab);setShowDock(true);}}>{tab}</button>)}<span className="spacer"/><button aria-label="Collapse engineering dock" onClick={()=>setShowDock(v=>!v)}>{showDock?'−':'+'}</button></div>
     {showDock&&<div className="dock-content" role="tabpanel">
      {(dock==='Timeline'||dock==='Telemetry')&&trajectory&&current&&<>
       <div className="transport"><button aria-label="Jump to start" onClick={()=>playback.seek(0)}><SkipBack size={14}/></button><button aria-label="Step backward" onClick={()=>playback.seek(index-1)}><StepBack size={14}/></button><button className="play-button" aria-label={playback.playing?'Pause recorded playback':'Play recorded playback'} onClick={playback.toggle}>{playback.playing?<Pause size={15}/>:<Play size={15}/>}</button><button aria-label="Step forward" onClick={()=>playback.seek(index+1)}><StepForward size={14}/></button><button aria-label="Jump to end" onClick={()=>playback.seek(samples.length-1)}><SkipForward size={14}/></button><button aria-label="Restart playback" onClick={()=>{playback.seek(0);}}><RotateCcw size={13}/></button>
        <code data-testid="playback-time">{current.time.toFixed(3)} / {samples.at(-1)!.time.toFixed(3)} s</code><span className="tiny">{index+1}/{samples.length} measured states</span><span className="spacer"/><label>Speed<select aria-label="Playback speed" value={playback.speed} onChange={e=>playback.setSpeed(Number(e.target.value))}>{[.25,.5,1,2].map(v=><option key={v} value={v}>{v}×</option>)}</select></label><label className="compare"><input type="checkbox" checked={compare} onChange={e=>setCompare(e.target.checked)}/>Compare baseline / verified</label>
       </div>
       <TimelineTracks trajectory={trajectory} index={index} onSeek={playback.seek}/>

       {dock==='Telemetry'&&<><p className="chart-legend">Teal: {labels[variant]} {compare?'· dashed amber: '+labels[variant==='original'?'attempt_2':'original']:''} · vertical cursor: selected measured timestamp · red: actual contact · dashed line: {experiment!.context.minimum_clearance_m} m minimum</p><Telemetry trajectory={trajectory} comparison={compare?experiment!.variants[variant==='original'?'attempt_2':'original']:undefined} index={index} onSeek={playback.seek} minimumClearance={experiment!.context.minimum_clearance_m}/></>}
       {dock==='Timeline'&&<div className="timeline-footer"><span className="note">601 measured states.</span><button onClick={()=>setDock('Telemetry')}>Inspect synchronized telemetry <ChevronRight size={12}/></button></div>}
      </>}
      {dock==='Verification'&&<><div className="verification-selector"><label>Recorded proposal<select aria-label="Review proposal" value={proposalVariant} onChange={e=>{setResumeId('');setReviewDiff(undefined);setProposalVariant(e.target.value as typeof proposalVariant);}}><option value="attempt_1">Proposal 1 · safety rejected</option><option value="attempt_2">Revision 2 · historical safety PASS</option></select></label></div>{experiment&&<Results experiment={experiment}/ >}{proposal&&<PatchReview key={proposalVariant} proposal={proposal} variant={proposalVariant} resumeId={resumeId} onDiff={source=>{setReviewDiff(source);setActive(DEFAULT_FILE);setTabs(t=>t.includes(DEFAULT_FILE)?t:[...t,DEFAULT_FILE]);setDiff(true);changeMode('code');}} onReview={review} errorReport={reportError}/>}</>}
      {dock==='Agent Activity'&&<div className="activity-list"><p className="note">RECORDED genuine model-selected calls. New live activity is shown in its separate agent session.</p>{recorded.calls.map((call,i)=><details key={i}><summary>{i+1}. {call.name}</summary><pre>{JSON.stringify(call,null,2)}</pre></details>)}</div>}
      {dock==='Console'&&<div className="console"><p><Terminal size={12}/> LOCAL WORKSPACE / ACTUAL ACTION LOG</p>{log.map((l,i)=><p key={i}>{l}</p>)}<button onClick={async()=>{try{const r=await api('prerequisites',{});setPrerequisites(r);}catch(e){reportError(String(e));}}}>Check credentials and VM qualification (no API call)</button>{prerequisites&&<pre>{JSON.stringify(prerequisites,null,2)}</pre>}</div>}
      {dock==='Problems'&&<p className="note">Monaco editor diagnostics and source-policy feedback are available in Code and Verification. A local draft is not source-validated or physically verified.</p>}
      {dock==='Output'&&<pre className="prose">{recorded.diagnosis}</pre>}
      {dock==='Tests'&&<div><p>RECORDED Day 6 regression: 350 passing tests.</p><p className="note">This is a prior saved result, not a newly executed test run. The IDE has no arbitrary shell/test-command endpoint.</p></div>}
      {dock==='Diagnostics'&&trajectory&&<pre>{JSON.stringify({recorded:true,scenario,source:labels[variant],summary:trajectory.summary,selected_measured_state:current},null,2)}</pre>}
      {dock==='Physics'&&<PhysicsPanel scenario={scenario} variant={variant}/>}
     </div>}
    </section></>}
   </main>
   {visibleAgent&&mode!=='agent'&&<Resize label="Resize agent" direction="right" value={layout.right} onChange={v=>resize('right',v)}/>}<div className="agent-container" hidden={!visibleAgent}><div className="right-tabs" hidden={mode==='agent'}><button aria-pressed={rightTab==='agent'} onClick={()=>setRightTab('agent')}>Agent</button><button aria-pressed={rightTab==='inspector'} onClick={()=>setRightTab('inspector')}>Inspector</button></div><div className="right-view" hidden={rightTab!=='agent'&&mode!=='agent'}><AgentPanel recorded={recorded} bootstrap={bootstrap} references={tabs} onFocus={focusAgent} onReview={review} onProposal={openProposal} onFile={path=>{void openFile(path);changeMode('code');}}/></div><div className="right-view inspector-view" hidden={rightTab!=='inspector'||mode==='agent'}><Inspector object={selected||undefined} scene={experiment?.scene} sample={current}/></div></div>

  </div>
  {extended?<footer className="statusbar"><span>{extended==='robustness'?'Frozen robustness contracts / candidate execution awaiting approval':'Engineering project / reviewed data changes / trusted simulation'}</span><span className="spacer"/><span>This view: no new API calls · $0.00</span><span>No hardware test claimed</span></footer>:<footer className="statusbar"><span title="Previously measured MuJoCo states. Pause freezes playback, not a live solver."><span className="status-dot"/>Recorded replay</span><span>Scenario {scenario} / {labels[variant]}</span><span className={trajectory?.summary.physical_safety_status==='PASS'?'success':'danger'}>{trajectory?'Recorded safety: '+trajectory.summary.physical_safety_status:'Loading evidence'}</span><span className="spacer"/>{resumeId&&<span>Review {resumeId.slice(0,8)}</span>}<span title={bootstrap.recording_sha256}>Evidence {bootstrap.recording_sha256.slice(0,10)}</span><span title="Opening and replaying the workspace makes no paid API requests.">View $0.00</span><span>{file?.historical?'Historical source':file&&drafts[active]!==undefined&&drafts[active]!==file.content?'Unsaved draft':'Original source'}</span></footer>}
 </div>;
}

function Results({experiment}:{experiment:Experiment}){
 return <div className="result-table"><p className="note">Recorded scenario {experiment.scenario} · historical A/B/C measurements are not new verification.</p><table><thead><tr><th>Controller</th><th>Min gap (m)</th><th>Final |v| (m/s)</th><th>Safety</th><th>Independent</th></tr></thead><tbody>{Object.entries(experiment.variants).map(([key,t])=><tr key={key}><td>{labels[key as Variant]}</td><td>{t.summary.minimum_clearance_m.toFixed(6)}</td><td>{t.summary.final_speed_ms.toPrecision(4)}</td><td className={t.summary.physical_safety_status==='PASS'?'success':'danger'}>{t.summary.physical_safety_status}</td><td>{t.summary.independent_verification}</td></tr>)}</tbody></table><p className="note">No wall contact · minimum gap ≥ 0.05 m · final |v| &lt; 0.03 m/s · completion ≤ 3 s</p></div>;
}

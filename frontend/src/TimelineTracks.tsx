import type {Trajectory} from './types';

const lanes=[{name:'Motion',labels:['Braking begins','End']},{name:'Contact',labels:['First contact']},{name:'Safety',labels:['Clearance violation']}] as const;
export function TimelineTracks({trajectory,index,onSeek}:{trajectory:Trajectory;index:number;onSeek:(index:number)=>void}){
 const last=trajectory.samples.length-1,duration=trajectory.samples[last].time;
 return <div className="event-timeline">
  <div className="timeline-ruler" aria-hidden="true"><span className="lane-label">Time</span><div>{Array.from({length:7},(_,i)=><span key={i} style={{left:`${i/6*100}%`}}>{(duration*i/6).toFixed(1)}s</span>)}</div></div>
  <div className="seek-row"><span className="lane-label">Seek</span><input aria-label="Measured timeline sample" type="range" min={0} max={last} step={1} value={index} onChange={e=>onSeek(Number(e.target.value))}/></div>
  <div className="event-lanes">{lanes.map(lane=>{
   const markers=trajectory.markers.filter(marker=>(lane.labels as readonly string[]).includes(marker.label));
   return <div className={'event-lane lane-'+lane.name.toLowerCase()} key={lane.name}><span className="lane-label">{lane.name}</span><div className="lane-track" aria-label={lane.name+' recorded events'}>
    <div className="lane-cursor" style={{left:`${index/last*100}%`}}/>
    {markers.map(marker=><button key={marker.label} style={{left:`${marker.index/last*100}%`}} title={`${marker.label} · ${marker.time.toFixed(3)} s · sample ${marker.index}`} aria-label={'Seek '+marker.label} onClick={()=>onSeek(marker.index)}><span aria-hidden="true">{marker.label==='End'?'│':marker.label==='Braking begins'?'◆':marker.label==='First contact'?'●':'▲'}</span></button>)}
    {!markers.length&&<small className="no-event">None recorded</small>}
   </div></div>;
  })}</div>
 </div>;
}

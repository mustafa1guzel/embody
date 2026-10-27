import {useMemo} from 'react';
import type {Sample,Trajectory} from './types';
const fields=[['position','Position','m'],['velocity','Velocity','m/s'],['wall_clearance','Clearance','m'],['generalized_actuator_force','Actuator force','N']] as const;
export function Telemetry({trajectory,comparison,index,onSeek,minimumClearance}:{trajectory:Trajectory;comparison?:Trajectory;index:number;onSeek:(index:number)=>void;minimumClearance?:number}){
 const current=trajectory.samples[index];
 const plots=useMemo(()=>fields.map(([field,label,unit])=>{
  const all=trajectory.samples.map(s=>Number(s[field]));if(comparison)for(const s of comparison.samples)all.push(Number(s[field]));
  const threshold=field==='wall_clearance'?minimumClearance:undefined;
  const min=Math.min(...all,threshold??0),max=Math.max(...all,threshold??0),span=max-min||1;
  const x=(s:Sample)=>40+s.time/trajectory.samples.at(-1)!.time*548;
  const y=(v:number)=>82-(v-min)/span*66;
  const path=(samples:Sample[])=>samples.map((s,i)=>`${i?'L':'M'}${x(s).toFixed(2)},${y(Number(s[field])).toFixed(2)}`).join(' ');
  return {field,label,unit,min,max,x,y,threshold,measured:path(trajectory.samples),comparison:comparison?path(comparison.samples):null};
 }),[trajectory,comparison,minimumClearance]);
 return <div className="telemetry-grid">{plots.map(({field,label,unit,min,max,x,y,threshold,measured,comparison:comparisonPath})=>{
  return <div className="plot" key={field}><div><span>{label}</span><strong data-testid={'value-'+field}>{Number(current[field]).toFixed(4)} <small>{unit}</small></strong></div>
   <svg viewBox="0 0 600 108" role="img" aria-label={label+' over measured time'} tabIndex={0} onKeyDown={event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();onSeek(Math.max(0,Math.min(trajectory.samples.length-1,index+(event.key==='ArrowRight'?1:-1))));}}} onClick={event=>{const rect=event.currentTarget.getBoundingClientRect();if(rect.width){const fraction=((event.clientX-rect.left)/rect.width*600-40)/548;onSeek(Math.max(0,Math.min(trajectory.samples.length-1,Math.round(fraction*(trajectory.samples.length-1)))));}}}>
    <line className="chart-axis" x1="40" y1="8" x2="40" y2="84"/><line className="chart-axis" x1="40" y1="84" x2="588" y2="84"/>
    <text className="axis-tick" x="34" y="20" textAnchor="end">{max.toFixed(2)}</text><text className="axis-tick" x="34" y="83" textAnchor="end">{min.toFixed(2)}</text>
    <text className="axis-tick" x="40" y="102">0 s</text><text className="axis-tick" x="588" y="102" textAnchor="end">{trajectory.samples.at(-1)!.time.toFixed(1)} s</text>
    {threshold!==undefined&&<><line x1="40" x2="588" y1={y(threshold)} y2={y(threshold)} className="threshold"/><text className="threshold-label" x="586" y={Math.max(10,y(threshold)-4)} textAnchor="end">{threshold} m minimum</text></>}
    {comparisonPath&&<path d={comparisonPath} className="comparison-path"/>}<path d={measured} className="measured-path"/>
    <line x1={x(current)} x2={x(current)} y1="8" y2="84" className="cursor" data-testid="chart-cursor"/>
    {trajectory.samples.filter(s=>s.wall_collision).map(s=><circle key={s.step} cx={x(s)} cy={y(Number(s[field]))} r="2" className="contact-dot"/>)}
   </svg></div>;
 })}</div>;
}

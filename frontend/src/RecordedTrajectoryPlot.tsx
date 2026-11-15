import {useEffect, useMemo, useState} from 'react';
import {displayNumber, recordedSeries, revisionNames, type Criteria, type RecordedRun, type Signal, type Scenario} from './physicsRegression';

type PlotRun = Pick<RecordedRun, 'id' | 'samples' | 'timeValid'> & {scenario?: Scenario; revision: RecordedRun['revision'] | 'reference'; title?: string};
const nameOf = (r: PlotRun) => r.title || (r.revision === 'reference' ? 'Trusted developer reference' : r.scenario + ' · ' + revisionNames[r.revision]);
const signals = {wall_clearance: ['Wall clearance', 'm'], velocity: ['Velocity', 'm/s'], position: ['Position', 'm']} as const;
export default function RecordedTrajectoryPlot({runs, criteria}: {runs: PlotRun[]; criteria: Criteria | null}) {
 const [signal, setSignal] = useState<Signal>('wall_clearance'), [index, setIndex] = useState(0);
 const series = useMemo(() => runs.map(run => ({run, points: recordedSeries(run, signal)})), [runs, signal]);
 const times = useMemo(() => [...new Set(series.flatMap(s => s.points.filter(p => p.value !== null).map(p => p.time)))].sort((a, b) => a - b), [series]);
 useEffect(() => setIndex(0), [runs, signal]);
 const values = series.flatMap(s => s.points.flatMap(p => p.value === null ? [] : [p.value]));
 const threshold = criteria ? signal === 'wall_clearance' ? criteria.minimumClearance : signal === 'velocity' ? criteria.maximumFinalSpeed : null : null;
 const cursor = times[Math.min(index, times.length - 1)];
 const minTime = times[0], maxTime = times.at(-1)!;
 const min = Math.min(...values, threshold ?? Infinity, signal === 'velocity' && threshold !== null ? -threshold : Infinity);
 const max = Math.max(...values, threshold ?? -Infinity);
 const padding = (max - min || 1) * 0.08;
 const x = (t: number) => 76 + (t - minTime) / (maxTime - minTime || 1) * 706;
 const y = (value: number) => 212 - (value - min + padding) / (max - min + 2 * padding) * 178;
 function path(points: typeof series[number]['points']) {
  let drawing = false;
  return points.map(p => {
   if (p.value === null) {drawing = false; return '';}
   const segment = `${drawing ? 'L' : 'M'}${x(p.time).toFixed(3)},${y(p.value).toFixed(3)}`;
   drawing = true; return segment;
  }).join(' ');
 }
 return <section className="regression-chart" aria-label="Recorded trajectory comparison">
  <div className="regression-section-heading"><h2>Recorded trajectories</h2><label>Signal<select aria-label="Trajectory signal" value={signal} onChange={e => setSignal(e.target.value as Signal)}>{Object.entries(signals).map(([key, [title, unit]]) => <option key={key} value={key}>{title} ({unit})</option>)}</select></label></div>
  {!times.length || !values.length ? <p role="status">No recorded signal is available for the selected overlays.</p> : <>
   <svg viewBox="0 0 820 254" role="img" aria-label={signals[signal][0] + ' compared over actual recorded time'}>
    <title>{signals[signal][0]} ({signals[signal][1]}) · actual recorded timestamps</title>
    {[0, 1, 2, 3].map(i => {const value = min + (max - min) * i / 3;return <g key={i}><line className="regression-gridline" x1="76" x2="782" y1={y(value)} y2={y(value)}/><text x="69" y={y(value) + 4} textAnchor="end">{displayNumber(value)}</text></g>;})}
    <text x="10" y="18">{signals[signal][1]}</text>
    {[0, 1, 2, 3, 4].map(i => {const t = minTime + (maxTime - minTime) * i / 4;return <text key={i} x={x(t)} y="238" textAnchor="middle">{displayNumber(t)} s</text>;})}
    {threshold !== null && <line className="regression-threshold" x1="76" x2="782" y1={y(threshold)} y2={y(threshold)}/>}
    {signal === 'velocity' && threshold !== null && <line className="regression-threshold" x1="76" x2="782" y1={y(-threshold)} y2={y(-threshold)}/>}
    {series.map(({run, points}) => <path key={run.id} data-testid={'trajectory-' + run.id} data-start={points[0]?.time} data-end={points.at(-1)?.time} d={path(points)} className={'regression-line regression-' + run.revision} strokeDasharray={run.scenario === 'B' ? '7 4' : run.scenario === 'C' ? '2 4' : undefined}/>)}
    <line className="regression-cursor" x1={x(cursor)} x2={x(cursor)} y1="25" y2="217"/>
   </svg>
   <label className="regression-scrubber">Inspect recorded timestamp<input aria-label="Recorded trajectory timestamp" type="range" min="0" max={times.length - 1} step="1" value={Math.min(index, times.length - 1)} onChange={e => setIndex(Number(e.target.value))}/><output>{displayNumber(cursor)} s</output></label>
   <ul className="regression-legend">{series.map(({run, points}) => {const sample = points.find(p => p.time === cursor);return <li key={run.id}><span className={'regression-swatch regression-' + run.revision}/><span>{nameOf(run)}</span><span>{sample?.value != null ? displayNumber(sample.value) + ' ' + signals[signal][1] : 'No sample at this timestamp'}</span></li>;})}</ul>
  </>}
  <p className="regression-note">{runs.every(r => r.scenario !== undefined) ? 'Solid: A · dashed: B · dotted: C. ' : 'Trusted developer reference recordings. '}Lines connect adjacent saved samples; missing values break the line. Each run keeps its actual time domain. No new samples or extrapolation. Dotted horizontal guides are hypothetical thresholds.</p>
 </section>;
}

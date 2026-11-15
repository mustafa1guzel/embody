import {useEffect, useMemo, useState} from 'react';
import {api} from './api';
import {displayNumber as n, draftOf, parseDraft, revisionNames, revisions, scenarios, type Criteria, type DraftCriteria, type Scenario} from './physicsRegression';
import type {Variant} from './types';
import {referencePlan,type DesignerTransfer} from './experimentDesigner';
import TrustedSweepPanel from './TrustedSweepPanel';
import RecordedTrajectoryPlot from './RecordedTrajectoryPlot';
import {axisValues, compareReference, defaultAxis, exportPlan, historicalCellState, limitations, makePlan, parameterKeys, parameters, parseAxis, parseNumber, parseSweepStudy, stateLabels, summarizePlan, type DraftAxis, type Parameter, type PhysicalParameters, type Plan, type SweepStudy} from './parameterSweep';
import './styles/physicsRegression.css';
import './styles/parameterSweep.css';

type Mode = 'prediction' | 'clearance' | 'status';
const criteriaFields: [keyof Criteria, string, string][] = [['minimumClearance', 'Required minimum clearance', 'm'], ['maximumFinalSpeed', 'Maximum final speed (exclusive)', 'm/s'], ['maximumSettlingTime', 'Maximum stopping / settling time', 's'], ['maximumContactEpisodes', 'Maximum contact episodes', 'episodes']];
const badge = (value: boolean) => value ? 'Predicted within limits' : 'Predicted outside limits';
function download(plan: Plan) {
 const url = URL.createObjectURL(new Blob([JSON.stringify(exportPlan(plan), null, 2) + '\n'], {type: 'application/json'}));
 const a = document.createElement('a');a.href = url;a.download = 'embody-rail-sweep-plan.json';a.click();setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function ParameterSweepLab({onClose, onOpenRegression,designerTransfer,onOpenDesigner}: {onClose?: () => void; onOpenRegression?: () => void;designerTransfer?:DesignerTransfer|null;onOpenDesigner?:()=>void}) {
 const [reviewedTransfer,setReviewedTransfer]=useState<DesignerTransfer|null>(null);
 const [data, setData] = useState<SweepStudy | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0);
 const [scenario, setScenario] = useState<Scenario>('A'), [revision, setRevision] = useState<Variant>('attempt_2');
 const [x, setX] = useState<DraftAxis>(defaultAxis('speed_mps')), [y, setY] = useState<DraftAxis | null>(defaultAxis('mass_kg'));
 const [fixed, setFixed] = useState<Record<Parameter, string>>({mass_kg: '2', speed_mps: '1.2', force_n: '4', gap_m: '1.77'}), [criteria, setCriteria] = useState<DraftCriteria | null>(null);
 const [plan, setPlan] = useState<Plan | null>(null), [selected, setSelected] = useState(''), [mode, setMode] = useState<Mode>('prediction');
 useEffect(() => {
  let alive = true;setData(null);setError('');setPlan(null);
  Promise.all(scenarios.map(s => api<unknown>('experiment?scenario=' + s))).then(parseSweepStudy).then(d => {
   if (alive) {setData(d);setCriteria(draftOf(d.study.defaults));setFixed(Object.fromEntries(parameterKeys.map(k => [k, String(d.references[0].parameters[k])])) as Record<Parameter, string>);}
  }).catch(e => {if (alive) setError(String(e));});
  return () => {alive = false;};
 }, [reload]);
 useEffect(()=>{
  if(!designerTransfer||!data)return;
  let alive=true;setPlan(null);setReviewedTransfer(null);
  api<DesignerTransfer>('experiment-designer/transfer?id='+designerTransfer.session_id+'&proposal='+designerTransfer.proposal_id).then(value=>{if(alive){setPlan(referencePlan(value));setReviewedTransfer(value);setSelected('designer:'+value.validated.cases[0].case_id);setCriteria(draftOf(value.validated.criteria));}}).catch(e=>{if(alive)setError('Reviewed transfer unavailable: '+String(e));});
  return()=>{alive=false;};
 },[designerTransfer,data]);
 function invalidate() {setPlan(null);setSelected('');}
 const proposal = useMemo(() => {
  if (!data || !criteria) return {plan: null, error: ''};
  try {
   const parsed = parseDraft(criteria);if (!parsed.criteria) throw new Error(parsed.errors.join(' '));
   const anchor = data.references.find(r => r.scenario === scenario)!;
   const p = Object.fromEntries(parameterKeys.map(k => [k, k === x.parameter || k === y?.parameter ? anchor.parameters[k] : parseNumber(fixed[k])])) as PhysicalParameters;
   return {plan: makePlan(data, scenario, revision, p, [parseAxis(x), ...(y ? [parseAxis(y)] : [])], parsed.criteria), error: ''};
  } catch (e) {return {plan: null, error: e instanceof Error ? e.message : String(e)};}
 }, [data, scenario, revision, fixed, x, y, criteria]);
 const active = plan?.cases.find(c => c.id === selected) || plan?.cases[0], summary = plan ? summarizePlan(plan) : null;
 const comparison = plan && active ? compareReference(active, plan.criteria) : null;
 const xValues = plan ? axisValues(plan.axes[0]) : [], yValues = plan?.axes[1] ? axisValues(plan.axes[1]) : [null];
 function reset() {
  if (!data) return;
  setScenario('A');setRevision('attempt_2');setX(defaultAxis('speed_mps'));setY(defaultAxis('mass_kg'));setMode('prediction');setCriteria(draftOf(data.study.defaults));
  setFixed(Object.fromEntries(parameterKeys.map(k => [k, String(data.references[0].parameters[k])])) as Record<Parameter, string>);invalidate();
 }
 function axisEditor(axis: DraftAxis, horizontal: boolean) {
  const title = horizontal ? 'Horizontal parameter' : 'Vertical parameter';
  function update(next: DraftAxis) {invalidate();if (horizontal) setX(next);else setY(next);}
  return <fieldset className="sweep-axis"><legend>{horizontal ? 'Horizontal axis' : 'Vertical axis'}</legend>
   <label>{title}<select aria-label={title} value={axis.parameter} onChange={e => update(defaultAxis(e.target.value as Parameter))}>{parameterKeys.map(k => <option key={k} value={k}>{parameters[k].label} ({parameters[k].unit})</option>)}</select></label>
   <div className="sweep-range">{(['minimum', 'maximum', 'step'] as const).map(k => <label key={k}>{k[0].toUpperCase() + k.slice(1)}<input aria-label={(horizontal ? 'Horizontal ' : 'Vertical ') + k} type="number" step="any" value={axis[k]} onChange={e => update({...axis, [k]: e.target.value})}/></label>)}</div>
   <small>{parameters[axis.parameter].low}–{parameters[axis.parameter].high} {parameters[axis.parameter].unit}; up to six decimals.</small>
  </fieldset>;
 }
 return <section className="sweep-lab regression-explorer" aria-label="Parameter Sweep Lab">
  <header className="regression-header"><div><span className="regression-eyebrow">Bounded rail experiment planning · EMBODY v0.4</span><h1>Parameter Sweep Lab</h1><p>Explore physical parameters before requesting an experiment.</p></div><div className="sweep-actions">{onOpenRegression && <button onClick={onOpenRegression}>Compare recorded controllers</button>}{onClose && <button onClick={onClose}>Back to workbench</button>}</div></header>
  <div className="regression-boundary"><strong>Analytical prediction ≠ measured physics.</strong> Analytical previews do not run physics. The separate trusted reference control below requires explicit confirmation. Saved anchor recordings remain historical.</div>
  {error ? <div role="alert" className="regression-error"><h2>Reference study unavailable</h2><p>{error}</p><p>No example or fallback result was substituted.</p><button onClick={() => setReload(v => v + 1)}>Retry saved reference read</button></div> : !data || !criteria ? <p role="status">Loading trusted reference metadata and saved measurements…</p> : <>
   <div className="sweep-layout"><aside className="sweep-config" aria-label="Experiment configuration">
    {reviewedTransfer?<><h2>Reviewed trusted-reference plan</h2><p>{reviewedTransfer.origin} · review only · NOT EXECUTED</p><p>Controller {reviewedTransfer.catalog.controller_id}</p><p>{reviewedTransfer.validated.case_count} exact validated cases. No historical A/B/C or repaired-controller identity is substituted.</p><p className="regression-hash">Proposal {reviewedTransfer.proposal_id}<br/>Source {reviewedTransfer.catalog.source_sha256}</p><p>Edit and review in the Designer before another transfer. The trusted panel still requires separate explicit simulation confirmation.</p>{onOpenDesigner&&<button onClick={onOpenDesigner}>Return to Experiment Designer</button>}</>:<><h2>1. Configure a bounded plan</h2><label>Reference experiment<select aria-label="Reference experiment" value={scenario} onChange={e => {
     const s = e.target.value as Scenario, ref = data.references.find(r => r.scenario === s)!;setScenario(s);setFixed(Object.fromEntries(parameterKeys.map(k => [k, String(ref.parameters[k])])) as Record<Parameter, string>);invalidate();
    }}>{scenarios.map(s => <option key={s} value={s}>Rail braking · scenario {s}</option>)}</select></label>
    <label>Recorded controller identity<select aria-label="Recorded controller identity" value={revision} onChange={e => {setRevision(e.target.value as Variant);invalidate();}}>{revisions.map(r => <option key={r} value={r}>{revisionNames[r]}</option>)}</select></label>
    <p className="regression-note">Controller choice binds the plan identity. Ideal braking predictions do not model its timing or run its source.</p>
    {axisEditor(x, true)}<label className="sweep-inline"><input type="checkbox" checked={y !== null} onChange={e => {setY(e.target.checked ? defaultAxis(x.parameter === 'mass_kg' ? 'speed_mps' : 'mass_kg') : null);invalidate();}}/>Vary a second parameter</label>{y && axisEditor(y, false)}
    <fieldset><legend>Fixed physical parameters</legend>{parameterKeys.filter(k => k !== x.parameter && k !== y?.parameter).map(k => <label key={k}>{parameters[k].label} ({parameters[k].unit})<input aria-label={'Fixed ' + parameters[k].label} type="number" step="any" value={fixed[k]} onChange={e => {setFixed({...fixed, [k]: e.target.value});invalidate();}}/></label>)}</fieldset>
    <details className="sweep-criteria"><summary>Acceptance criteria</summary><p>Ideal preview checks clearance and ideal stopping time only. Speed/contact criteria apply to saved measurements through the existing Regression Explorer evaluator.</p>{criteriaFields.map(([k, title, unit]) => <label key={k}>{title} ({unit})<input aria-label={title} type="number" step={k === 'maximumContactEpisodes' ? '1' : 'any'} value={criteria[k]} onChange={e => {setCriteria({...criteria, [k]: e.target.value});invalidate();}}/></label>)}</details>
    <div className="sweep-count" aria-live="polite">{proposal.plan ? <><strong>{proposal.plan.cases.length}</strong> proposed experiments · maximum 25</> : 'No valid experiment grid'}</div>
    {proposal.error && <p role="alert" className="regression-error">{proposal.error} No cases can be previewed or exported.</p>}
    <button className="sweep-primary" disabled={!proposal.plan} onClick={() => {setPlan(proposal.plan);setSelected(proposal.plan!.cases[0].id);}}>Preview analytical plan</button><button onClick={reset}>Reset to defaults</button>
    <small className="regression-note">Changing inputs clears the displayed plan. A maximum is an inclusive bound; an endpoint is included only if reached by whole steps. Nothing runs on edit or preview.</small></>}
   </aside><main className="sweep-content">
    {!plan || !active || !summary ? <div className="sweep-empty"><span className="regression-eyebrow">Plan → predict → review</span><h2>Design the experiment before execution</h2><p>The default grid explores three masses and three initial velocities. Preview it to see nine ideal braking predictions and any exact-anchor historical comparison.</p><p>Previewing does not run a solver or provider. The trusted developer reference below can execute only after separate explicit confirmation.</p></div> : <>
     <section className="regression-summary" aria-label="Sweep summary"><div><span>{reviewedTransfer?'Preview only · execution tracked separately':'Executions of this historical-controller plan'}</span><strong>{reviewedTransfer?plan.cases.length+' planned':'0 / '+plan.cases.length}</strong><small>{reviewedTransfer?'Use native results below; link the saved sweep in the Designer.':'Every case is NOT EXECUTED'}</small></div><div><span>Within ideal limits</span><strong>{summary.predicted_within} / {plan.cases.length}</strong><small>Analytical prediction only</small></div><div><span>Smallest predicted clearance margin</span><strong>{n(summary.smallest_margin_m)} m</strong><small>Sampled plan, no safety guarantee</small></div></section>
     <div className="sweep-review-layout"><section className="sweep-grid-section" aria-label="Parameter heatmap"><div className="regression-section-heading"><h2>2. Inspect the parameter grid</h2><label>Heatmap mode<select aria-label="Heatmap mode" value={mode} onChange={e => setMode(e.target.value as Mode)}><option value="prediction">Analytical predicted clearance</option><option value="clearance">Historical measured minimum clearance</option><option value="status">Historical measured acceptance status</option></select></label></div>
      <p className="regression-note">{mode === 'prediction' ? 'Each cell is an ideal prediction, never a measured PASS.' : 'Only exact-anchor recordings are shown. Saved-data evaluation uses your selected criteria; its original verdict stays fixed. Every new case remains unexecuted.'}</p>
      <div className="regression-table-scroll"><table className="sweep-grid"><caption>{plan.axes[1] ? parameters[plan.axes[1].parameter].label + ' ↓ · ' : 'One-dimensional sweep · '}{parameters[plan.axes[0].parameter].label} →</caption><thead><tr><th scope="col">{plan.axes[1] ? parameters[plan.axes[1].parameter].unit : 'Case'}</th>{xValues.map(v => <th scope="col" key={v}>{n(v)} {parameters[plan.axes[0].parameter].unit}</th>)}</tr></thead><tbody>{yValues.map((v, row) => <tr key={row}><th scope="row">{v === null ? '1' : n(v)}</th>{xValues.map((_, col) => {
       const c = plan.cases[row * xValues.length + col], ref = compareReference(c, plan.criteria), within = c.prediction.classification === 'WITHIN_IDEAL_LIMITS';
       const color = mode === 'prediction' ? within ? 'ideal-within' : 'ideal-outside' : ref ? historicalCellState(c, plan.criteria).toLowerCase() : 'unavailable';
       return <td key={c.id}><button data-testid={'sweep-cell-' + (row * xValues.length + col)} aria-label={'Inspect case ' + (row * xValues.length + col + 1) + ': ' + parameterKeys.map(k => parameters[k].label + ' ' + c.parameters[k] + ' ' + parameters[k].unit).join(', ')} aria-pressed={active.id === c.id} className={'sweep-cell ' + color + (active.id === c.id ? ' selected' : '')} onClick={() => setSelected(c.id)}>
        <strong>{mode === 'prediction' ? n(c.prediction.remaining_clearance_m) + ' m' : mode === 'clearance' ? ref?.measured_minimum_clearance_m != null ? n(ref.measured_minimum_clearance_m) + ' m' : 'Unavailable' : ref ? 'Derived ' + ref.evaluation.status.replaceAll('_', ' ') : 'Insufficient data'}</strong>
        <span>{mode === 'prediction' ? badge(within) : ref ? 'Saved scenario ' + c.savedReference!.scenario + ' · recorded ' + ref.recordedVerdict : 'No exact-anchor recording'}</span><small>Not executed</small>
       </button></td>;
      })}</tr>)}</tbody></table></div>
      <p className="sweep-legend"><b>Legend:</b> {mode === 'prediction' ? 'Teal + “within”: ideal clearance/time limits met · amber + “outside”: at least one ideal limit missed.' : 'Teal: derived PASS over saved measurements · amber: derived FAIL · gray: insufficient or no matching saved data.'} Text labels accompany every color.</p>
      <details><summary>Execution states and availability</summary><ul>{Object.entries(stateLabels).map(([k, text]) => <li key={k}>{text}{['RUNNING', 'EXECUTION_ERROR', 'MEASURED_PASS', 'MEASURED_FAIL'].includes(k) ? ' — not an execution state of this historical-controller plan; see the separate trusted reference' : ''}</li>)}</ul><p>Recorded reader errors block reference loading; they are never substituted for physics execution errors or successful measurements.</p></details>
     </section><aside className="sweep-detail" aria-label="Selected experiment details"><h2>3. Review case {plan.cases.indexOf(active) + 1}</h2><span className="sweep-status">{reviewedTransfer?'ANALYTICAL PREVIEW · no measured data attached':'NOT EXECUTED · review only'}</span><dl>{parameterKeys.map(k => <div key={k}><dt>{parameters[k].label}</dt><dd>{n(active.parameters[k])} {parameters[k].unit}</dd></div>)}</dl>
      <h3>Analytical prediction</h3><dl><div><dt>Maximum ideal deceleration</dt><dd>{n(active.prediction.deceleration_mps2)} m/s²</dd></div><div><dt>Ideal stopping distance</dt><dd>{n(active.prediction.stopping_distance_m)} m</dd></div><div><dt>Ideal stopping time</dt><dd>{n(active.prediction.stopping_time_s)} s</dd></div><div><dt>Remaining clearance</dt><dd>{n(active.prediction.remaining_clearance_m)} m</dd></div><div><dt>Clearance margin</dt><dd>{n(active.prediction.clearance_margin_m)} m</dd></div><div><dt>Time margin</dt><dd>{n(active.prediction.time_margin_s)} s</dd></div></dl><p>{badge(active.prediction.classification === 'WITHIN_IDEAL_LIMITS')}; only clearance/time are predicted.</p>
      {comparison ? <section aria-label="Historical anchor comparison"><h3>Saved recording · {active.savedReference!.scenario}</h3><p>Original verdict: <strong>{comparison.recordedVerdict}</strong><br/>Derived selected criteria: <strong>{comparison.evaluation.status.replaceAll('_', ' ')}</strong></p><p>Measured minimum clearance: {n(comparison.measured_minimum_clearance_m)} m<br/>Measured minus ideal clearance: {n(comparison.clearance_minus_ideal_m)} m</p><p>Sampled low-speed suffix: {n(comparison.sampled_settling_time_s)} s<br/>Travel to that sample: {n(comparison.sampled_settling_travel_m)} m<br/>Travel minus ideal stop distance: {n(comparison.travel_minus_ideal_m)} m</p><p className="regression-note">Sampled speed-threshold settling and ideal exact rest have different definitions. Differences may involve timing, integration, contact or model assumptions; this comparison alone does not establish a cause.</p></section> : <p role="status">{reviewedTransfer?'No measured data attached to this preview. Inspect a separate saved native run below and link it in the Designer.':'Insufficient data: no exact-anchor saved recording for this case. No measured trajectory exists for this historical-controller case.'}</p>}
      <details><summary>Exact plan / case identity</summary><p className="regression-hash">{active.id}</p><p className="regression-hash">{plan.controller_revision==='reference'?'Designer context':'Recording inventory'}: {plan.inventory_sha256}</p><p>Model: {plan.model_id} · {plan.controller_revision==='reference'?'Trusted developer reference':revisionNames[plan.controller_revision]}. Fixed initial position, geometry, timestep and duration follow the selected anchor or registered trusted reference; gap moves the wall center at fixed wall size.</p></details>
     </aside></div>
     <section className="sweep-analysis" aria-label="Failure boundary analysis"><h2>Sampled boundaries and remaining unknowns</h2><p>{summary.historical_comparisons} exact-anchor historical comparison(s); {summary.historical_hypothetical_passes} meet the selected measured criteria; {summary.disagreements} disagree with the ideal clearance/time classification. Worst historical clearance in this plan: {n(summary.worst_historical_clearance_m)} m.</p><p>{summary.predicted_transitions.length} adjacent sampled transitions in the <strong>analytical prediction</strong>. {summary.predicted_transitions.length ? 'These bracket ideal sampled changes, not observed physical failure boundaries.' : 'No ideal transition in this grid; this is not a universal safety envelope.'}</p>{summary.predicted_transitions.length > 0 && <details><summary>Inspect ideal sampled transition brackets</summary><ul>{summary.predicted_transitions.map(t => {const a = plan.cases.find(c => c.id === t.from)!, b = plan.cases.find(c => c.id === t.to)!;return <li key={t.from + t.to}>{parameters[t.parameter].label}: {n(a.parameters[t.parameter])}–{n(b.parameters[t.parameter])} {parameters[t.parameter].unit}; {parameterKeys.filter(k => k !== t.parameter).map(k => parameters[k].label + ' ' + n(a.parameters[k]) + ' ' + parameters[k].unit).join(', ')} fixed. Analytical classification changes between these samples only.</li>;})}</ul></details>}<p>This analytical/historical plan has no new physical executions. Separate trusted-reference results below belong to their own request. Historical evidence is not relabelled as a new sweep.</p></section>
     {active.savedReference && <RecordedTrajectoryPlot runs={[active.savedReference.run]} criteria={plan.criteria}/>}
     <div className="sweep-export"><button onClick={() => download(plan)}>Export plan JSON</button><p>Portable parameters, units, criteria, analytical predictions and separately labelled historical comparison. New measured results remain null.</p></div>
    </>}
    <TrustedSweepPanel plan={plan}/>
    <details className="sweep-assumptions"><summary>Mathematical model, supported mappings and limitations</summary><p>a = F / m · d = m × v² / (2F) · t = m × v / F. Distance means axial travel from the initial bumper; remaining clearance = initial surface gap − d.</p><ul>{limitations.map(text => <li key={text}>{text}</li>)}</ul><p>Mass 1–4 kg and force 2–6 N use the existing bounded rail envelope. Gap 0.35–2.2 m maps to the fixed-size wall center. Speed 0–1.2 m/s uses the BODYBASE initial-speed ceiling; stationary cases are analytical-only and extend below the historical robustness sampler's 0.4 m/s floor. Geometry, initial position, timestep and duration cannot be swept here.</p><ul>{parameterKeys.map(k => <li key={k}>{parameters[k].label}: {parameters[k].mapping}</li>)}</ul></details>
   </main></div>
  </>}
 </section>;
}

import {useEffect, useMemo, useState} from 'react';
import {api} from './api';
import type {FileData, Proposal, Variant} from './types';
import {displayNumber as n, draftOf, evaluateRun, parseDraft, parseStudy, revisionComparison, revisionNames, revisions, scenarios, summarize, type Criteria, type Criterion, type DraftCriteria, type RecordedRun, type Scenario, type Study} from './physicsRegression';
import RecordedTrajectoryPlot from './RecordedTrajectoryPlot';
import './styles/physicsRegression.css';

const rankNames = {clearance: 'Clearance margin (m)', speed: 'Final-speed headroom (m/s)', settling: 'Settling-time headroom (s)', contacts: 'Contact-episode headroom'};
const fields: [keyof Criteria, string, string][] = [['minimumClearance', 'Minimum wall clearance', 'm'], ['maximumFinalSpeed', 'Maximum final speed (exclusive)', 'm/s'], ['maximumSettlingTime', 'Maximum settling time', 's'], ['maximumContactEpisodes', 'Maximum wall contact episodes', 'episodes']];
const statusLabel = (status: string) => status === 'INSUFFICIENT_DATA' ? 'Insufficient data' : status;

function ControllerSource({run}: {run: RecordedRun}) {
 const [result, setResult] = useState<{source: string; diff?: string} | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [showDiff, setShowDiff] = useState(true);
 useEffect(() => {setResult(null);setError('');setBusy(false);}, [run.id]);
 useEffect(() => {
  if (!busy) return;
  let alive = true;
  (async () => {
   const data = run.revision === 'original' ? await api<FileData>('file?path=robot%2Fcontroller.py') : await api<Proposal>('proposal?variant=' + run.revision);
   const source = 'source' in data ? data.source : data.content;
   const raw = new TextEncoder().encode(source);
   const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(v => v.toString(16).padStart(2, '0')).join('');
   if (hash !== run.controllerSha256) throw new Error('Saved controller source differs from this experiment identity.');
   if (alive) setResult({source, diff: 'diff' in data ? data.diff : undefined});
  })().catch(e => {if (alive) setError(String(e));}).finally(() => {if (alive) setBusy(false);});
  return () => {alive = false;};
 }, [busy, run.id, run.revision, run.controllerSha256]);
 return <details className="regression-source"><summary>Inspect saved controller revision</summary>
  <p className="regression-note">Read-only saved source. Opening this view grants no execution or application authority.</p><p className="regression-hash">Controller SHA-256: {run.controllerSha256 || 'Unavailable'}</p>
  {!result && <button disabled={busy || !run.controllerSha256} onClick={() => setBusy(true)}>{busy ? 'Reading saved source…' : 'Load saved source'}</button>}
  {error && <p role="alert">Source unavailable: {error}</p>}
  {result && <>{result.diff && <label className="regression-inline"><input type="checkbox" checked={showDiff} onChange={e => setShowDiff(e.target.checked)}/>Show recorded diff from original</label>}<pre tabIndex={0} aria-label="Saved controller source">{showDiff && result.diff ? result.diff : result.source}</pre></>}
 </details>;
}

export default function PhysicsRegressionExplorer({onClose}: {onClose?: () => void}) {
 const [study, setStudy] = useState<Study | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0), [draft, setDraft] = useState<DraftCriteria | null>(null);
 const [selectedScenarios, setSelectedScenarios] = useState<Scenario[]>([...scenarios]), [selectedRevisions, setSelectedRevisions] = useState<Variant[]>([...revisions]);
 const [active, setActive] = useState('A:attempt_2'), [ranking, setRanking] = useState<Criterion>('clearance'), [overlays, setOverlays] = useState(['A:original', 'A:attempt_1', 'A:attempt_2']);
 useEffect(() => {
  let alive = true;setStudy(null);setError('');setDraft(null);
  Promise.all(scenarios.map(s => api<unknown>('experiment?scenario=' + s))).then(parseStudy).then(s => {if (alive) {setStudy(s);setDraft(draftOf(s.defaults));}}).catch(e => {if (alive) setError(String(e));});
  return () => {alive = false;};
 }, [reload]);
 const parsed = useMemo(() => draft ? parseDraft(draft) : {criteria: null, errors: []}, [draft]);
 const runs = useMemo(() => study?.runs.filter(r => selectedScenarios.includes(r.scenario) && selectedRevisions.includes(r.revision)) || [], [study, selectedScenarios, selectedRevisions]);
 const evaluations = useMemo(() => parsed.criteria ? runs.map(r => evaluateRun(r, parsed.criteria!)) : [], [runs, parsed.criteria]);
 const summary = useMemo(() => summarize(evaluations, ranking), [evaluations, ranking]);
 const comparisons = useMemo(() => study && parsed.criteria ? revisionComparison(study.runs.filter(r => selectedScenarios.includes(r.scenario)), parsed.criteria) : [], [study, parsed.criteria, selectedScenarios]);
 const overlayRuns = useMemo(() => runs.filter(r => overlays.includes(r.id)), [runs, overlays]);
 const activeRun = runs.find(r => r.id === active) || runs[0];
 const detail = evaluations.find(e => e.run.id === activeRun?.id);
 const availableClearances = runs.flatMap(r => r.minimumClearance === null ? [] : [r.minimumClearance]);
 const observedWorstClearance = availableClearances.length ? Math.min(...availableClearances) : null;
 function toggle<T>(values: T[], value: T): T[] {return values.includes(value) ? values.filter(x => x !== value) : [...values, value];}
 return <section className="regression-explorer" aria-label="Physics Regression Explorer">
  <header className="regression-header"><div><span className="regression-eyebrow">Recorded rail-braking study · EMBODY v0.2.1</span><h1>Physics Regression Explorer</h1><p>Compare controller revisions against the same recorded scenarios.</p></div>{onClose && <button onClick={onClose}>Back to workbench</button>}</header>
  <div className="regression-boundary"><strong>Historical verdicts stay fixed.</strong> Thresholds below produce a separate hypothetical evaluation of saved measurements. No new simulation, model call or controller execution.</div>
  {error ? <div role="alert" className="regression-error"><h2>Recorded study unavailable</h2><p>{error}</p><p>No fallback measurements or verdicts were substituted.</p><button onClick={() => setReload(n => n + 1)}>Retry saved-data read</button></div> : !study || !draft ? <p role="status">Loading recorded scenarios A, B and C…</p> : <>
   <div className="regression-toolbar"><fieldset><legend>Recorded scenarios</legend>{scenarios.map(s => <label key={s}><input type="checkbox" checked={selectedScenarios.includes(s)} onChange={() => setSelectedScenarios(v => toggle(v, s))}/>Scenario {s}</label>)}</fieldset><fieldset><legend>Controller revisions</legend>{revisions.map(v => <label key={v}><input type="checkbox" checked={selectedRevisions.includes(v)} onChange={() => setSelectedRevisions(old => toggle(old, v))}/>{revisionNames[v]}</label>)}</fieldset></div>
   <div className="regression-layout"><aside className="regression-criteria" aria-label="Hypothetical acceptance criteria"><h2>Hypothetical criteria</h2><p className="regression-note">Defaults come from the original documented task. Adjusting them never changes a recorded verdict.</p>
    {fields.map(([key, label, unit]) => <label key={key}>{label}<span className="regression-input"><input type="number" min="0" step={key === 'maximumContactEpisodes' ? '1' : 'any'} aria-label={label} value={draft[key]} aria-invalid={parsed.errors.length ? true : undefined} aria-describedby="regression-rules" onChange={e => setDraft({...draft, [key]: e.target.value})}/><span>{unit}</span></span></label>)}
    <button onClick={() => setDraft(draftOf(study.defaults))}>Reset to recorded criteria</button>
    {parsed.errors.length > 0 && <div role="alert" className="regression-error"><strong>Invalid hypothetical criteria</strong><ul>{parsed.errors.map(s => <li key={s}>{s}</li>)}</ul><p>Derived results are withheld until corrected.</p></div>}
    <details id="regression-rules"><summary>Evaluation rules and limitations</summary><p>Clearance is inclusive with the existing 1e−12 m tolerance. Final absolute speed is strictly below its limit. Contact episodes count rising edges, rather than individual contact points or samples.</p><p>Settling time is newly derived: the earliest saved sample after which all remaining saved speeds stay strictly below the selected speed limit. It is not an exact zero-speed stopping time. The default 3-second deadline comes from the recorded completion criterion; the historical verdict still includes its original complete-horizon and finite-measurement checks.</p><p>No observed settling before a deadline covered by the recording fails. If that deadline extends beyond the available horizon, the result is insufficient data. Equality at the speed limit fails; clearance and time allow their stated tolerance.</p><p>Results cover these finite saved cases only. They do not establish physical behavior after the recorded horizon or real-world safety.</p></details>
   </aside><main className="regression-content">
    {!runs.length ? <p role="status">Select at least one scenario and controller revision.</p> : <>
     <section className="regression-summary" aria-label="Derived engineering summary" aria-live="polite"><div><span>Hypothetical passes</span><strong>{parsed.criteria ? summary.passed + ' / ' + runs.length : 'Withheld'}</strong><small>{parsed.criteria ? summary.failed + ' fail · ' + summary.insufficient + ' insufficient' : 'Correct the criteria'}</small></div><div><span>Worst observed clearance</span><strong>{n(observedWorstClearance)}{observedWorstClearance !== null ? ' m' : ''}</strong><small>Across selected recorded runs</small></div><div><span>Recorded passes · immutable</span><strong>{runs.filter(r => r.recordedVerdict === 'PASS').length} / {runs.length}</strong><small>Original experiment verdicts</small></div></section>
     <section className="regression-matrix-section"><div className="regression-section-heading"><h2>Scenario × controller comparison</h2><span className="regression-note">Recorded / hypothetical are separate results</span></div><div className="regression-table-scroll"><table className="regression-matrix"><caption className="sr-only">Recorded verdicts, hypothetical threshold results and physical measurements</caption><thead><tr><th scope="col">Scenario</th>{revisions.filter(v => selectedRevisions.includes(v)).map(v => <th scope="col" key={v}>{revisionNames[v]}</th>)}</tr></thead><tbody>{scenarios.filter(s => selectedScenarios.includes(s)).map(s => <tr key={s}><th scope="row">{s}</th>{revisions.filter(v => selectedRevisions.includes(v)).map(v => {
      const run = runs.find(r => r.scenario === s && r.revision === v)!, e = evaluations.find(e => e.run.id === run.id);
      return <td key={v}><button className={'regression-cell' + (activeRun?.id === run.id ? ' selected' : '')} aria-label={'Inspect scenario ' + s + ' · ' + revisionNames[v]} aria-pressed={activeRun?.id === run.id} onClick={() => setActive(run.id)}>
       <span>Recorded <b className={'regression-status status-' + run.recordedVerdict}>{run.recordedVerdict}</b></span><span>Hypothetical <b className={'regression-status status-' + (e?.status || 'INVALID')}>{e ? statusLabel(e.status) : 'Withheld'}</b></span>
       <span className="regression-cell-metrics"><span>Min gap <b>{n(run.minimumClearance)} m</b></span><span>Final |v| <b>{n(run.finalSpeed)} m/s</b></span><span>Contacts <b>{n(run.contactEpisodes)} episodes</b></span></span>
      </button></td>;
     })}</tr>)}</tbody></table></div></section>
     <fieldset className="regression-overlays"><legend>Trajectory overlays</legend>{runs.map(run => <label key={run.id}><input type="checkbox" checked={overlays.includes(run.id)} onChange={() => setOverlays(v => toggle(v, run.id))}/>{run.scenario} · {revisionNames[run.revision]}</label>)}</fieldset>
     <RecordedTrajectoryPlot runs={overlayRuns} criteria={parsed.criteria}/>
     {parsed.criteria && <section className="regression-ranking" aria-label="Worst recorded cases"><label>Rank remaining margin by<select value={ranking} onChange={e => setRanking(e.target.value as Criterion)}>{Object.entries(rankNames).map(([k, name]) => <option key={k} value={k}>{name}</option>)}</select></label><p><strong>Smallest selected margin:</strong> {summary.worst.length ? summary.worst.map(e => e.run.scenario + ' · ' + revisionNames[e.run.revision]).join(', ') + ' (' + n(summary.margin) + ' ' + summary.worst[0].checks.find(c => c.criterion === ranking)!.unit + ')' : 'Insufficient recorded data'}.</p><p className="regression-note">{summary.ranked} of {runs.length} runs have this margin. Each ranking uses one physical unit; unlike units are never combined into a safety score. A zero margin at an exclusive speed limit still fails.</p><p>Most frequently failing criterion: {summary.mostRestrictive.length ? summary.mostRestrictive.map(x => x.criterion + ' (' + x.count + ' runs)').join(', ') : 'None in the available selected measurements'}.</p></section>}
     {activeRun && <section className="regression-detail" aria-label="Selected run details"><h2>Scenario {activeRun.scenario} · {revisionNames[activeRun.revision]}</h2><p>Recorded verdict: <strong>{activeRun.recordedVerdict}</strong> · recorded independent execution: <strong>{activeRun.independentVerdict}</strong></p><dl><dt>Maximum absolute velocity</dt><dd>{n(activeRun.maximumSpeed)} m/s</dd><dt>Sampled low-speed suffix begins</dt><dd>{detail?.settledAt != null ? n(detail.settledAt) + ' s' : parsed.criteria ? 'Not observed or unavailable' : 'Withheld — invalid criteria'}</dd><dt>Recorded time domain</dt><dd>{n(activeRun.firstTime)}–{n(activeRun.lastTime)} s</dd><dt>Contact samples</dt><dd>{n(activeRun.contactSamples)} (distinct from episodes)</dd></dl>
      {detail && <ul className="regression-checks">{detail.checks.map(c => <li key={c.criterion}><strong className={'status-' + c.status}>{statusLabel(c.status)} · {c.label}</strong><span>{c.explanation}</span><small>Measured: {n(c.value)} {c.unit} · remaining margin: {n(c.margin)} {c.unit}</small></li>)}</ul>}
      <details><summary>Original recorded failure explanations</summary><ul>{activeRun.recordedFailures.length ? activeRun.recordedFailures.map(s => <li key={s}>{s}</li>) : <li>No recorded failure reason; missing reasons alone are not proof of PASS.</li>}</ul></details>
      {activeRun.notes.length > 0 && <ul role="status">{activeRun.notes.map(note => <li key={note}>{note}</li>)}</ul>}
      <ControllerSource key={activeRun.id} run={activeRun}/>
     </section>}
     <section className="regression-progression"><h2>Controller progression</h2><p className="regression-note">Same selected scenarios; each revision is evaluated separately. Removing a revision column does not remove this comparison.</p><div>{comparisons.map((c, i) => {const previous = comparisons[i - 1];return <article key={c.revision}><h3>{revisionNames[c.revision]}</h3><p>{c.passed} / {c.runs} hypothetical passes</p><p>Worst observed clearance: {n(c.worstClearance)} m</p>{previous && <p>Change in worst observed clearance: {n(c.worstClearance !== null && previous.worstClearance !== null ? c.worstClearance - previous.worstClearance : null)} m</p>}</article>;})}</div></section>

    </>}
    <footer className="regression-evidence"><details><summary>Recording identity and scope</summary><p className="regression-hash">Inventory SHA-256: {study.inventorySha256}</p><p>The existing bounded reader owns source identity and recorded verification. This explorer performs deterministic arithmetic and displays the saved controller source; it neither reruns independent verification nor grants execution approval.</p></details><p>Passing all selected recorded scenarios does not establish generalization beyond these scenarios or certify a real robot.</p></footer>
   </main></div>
  </>}
 </section>;
}

/** Read-only analysis of recorded samples. No engine, controller or execution API. */
import type {Variant} from './types';

export const scenarios = ['A', 'B', 'C'] as const;
export const revisions: Variant[] = ['original', 'attempt_1', 'attempt_2'];
export const revisionNames: Record<Variant, string> = {original: 'Original controller', attempt_1: 'First repair', attempt_2: 'Second repair'};
export type Scenario = typeof scenarios[number];
export type Verdict = 'PASS' | 'FAIL' | 'UNAVAILABLE';
export type EvaluationStatus = 'PASS' | 'FAIL' | 'INSUFFICIENT_DATA';
export type Criterion = 'clearance' | 'speed' | 'settling' | 'contacts';
export type Signal = 'position' | 'velocity' | 'wall_clearance';
export type Criteria = {minimumClearance: number; maximumFinalSpeed: number; maximumSettlingTime: number; maximumContactEpisodes: number};
export type DraftCriteria = Record<keyof Criteria, string>;
export type RecordedSample = {time: number; position: number | null; velocity: number | null; wall_clearance: number | null; wall_collision: boolean | null};
export type RecordedRun = {
 id: string; scenario: Scenario; revision: Variant; recordedVerdict: Verdict; independentVerdict: Verdict;
 controllerSha256: string; inventorySha256: string; samples: RecordedSample[]; timeValid: boolean;
 minimumClearance: number | null; finalSpeed: number | null; maximumSpeed: number | null;
 contactEpisodes: number | null; contactSamples: number | null; firstTime: number | null; lastTime: number | null;
 notes: string[]; recordedFailures: string[];
};
export type Check = {criterion: Criterion; label: string; status: EvaluationStatus; value: number | null; margin: number | null; unit: string; explanation: string};
export type Evaluation = {run: RecordedRun; status: EvaluationStatus; checks: Check[]; settledAt: number | null};
export type Study = {runs: RecordedRun[]; defaults: Criteria; inventorySha256: string};
const tolerance = 1e-12; // Existing clearance/time comparison tolerance; speed remains strictly exclusive.
const object = (v: unknown): Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v) ? v as Record<string, unknown> : {};
export const finite = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) ? v : null;
const verdict = (v: unknown): Verdict => v === 'PASS' || v === 'FAIL' ? v : 'UNAVAILABLE';
const hash = (v: unknown): string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v) ? v : '';

export function validateCriteria(v: unknown): string[] {
 const c = object(v), errors: string[] = [];
 for (const [key, title] of [['minimumClearance', 'Minimum clearance'], ['maximumFinalSpeed', 'Maximum final speed'], ['maximumSettlingTime', 'Maximum settling time'], ['maximumContactEpisodes', 'Maximum contact episodes']] as const) {
  const n = finite(c[key]);
  if (n === null || n < 0 || (key === 'maximumFinalSpeed' && n === 0) || (key === 'maximumContactEpisodes' && !Number.isSafeInteger(n)))
   errors.push(title + (key === 'maximumFinalSpeed' ? ' must be a finite positive number.' : key === 'maximumContactEpisodes' ? ' must be a nonnegative safe integer.' : ' must be a finite nonnegative number.'));
 }
 return errors;
}
export function parseDraft(draft: DraftCriteria): {criteria: Criteria | null; errors: string[]} {
 const value = Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, v.trim() === '' ? NaN : Number(v)]));
 const errors = validateCriteria(value);
 return {criteria: errors.length ? null : value as Criteria, errors};
}
export const draftOf = (c: Criteria): DraftCriteria => Object.fromEntries(Object.entries(c).map(([k, v]) => [k, String(v)])) as DraftCriteria;

function extractRun(scenario: Scenario, revision: Variant, raw: unknown, inventory: string): RecordedRun {
 const t = object(raw), summary = object(t.summary), acceptance = object(summary.safety_acceptance), independent = object(t.independent);
 if (summary.scenario_id !== undefined && summary.scenario_id !== scenario) throw new Error('Recorded scenario identity differs.');
 const recordedVerdict = verdict(summary.physical_safety_status);
 if (acceptance.status !== undefined && verdict(acceptance.status) !== recordedVerdict) throw new Error('Conflicting recorded verdicts.');
 const notes: string[] = [], rows = Array.isArray(t.samples) ? t.samples.map(object) : [];
 const timeValid = rows.length > 0 && rows.every((s, i) => finite(s.time) !== null && (i === 0 || Number(s.time) > Number(rows[i - 1].time)));
 if (!timeValid) notes.push('Missing, nonfinite or non-increasing timestamps: trajectory and settling time unavailable.');
 const samples: RecordedSample[] = timeValid ? rows.map(s => ({time: s.time as number, position: finite(s.position), velocity: finite(s.velocity), wall_clearance: finite(s.wall_clearance), wall_collision: typeof s.wall_collision === 'boolean' ? s.wall_collision : null})) : [];
 function values(key: 'velocity' | 'wall_clearance'): number[] | null {
  return rows.length && rows.every(s => finite(s[key]) !== null) ? rows.map(s => s[key] as number) : null;
 }
 function consistent(name: string, saved: unknown, measured: number | null, count = false): number | null {
  const n = finite(saved), valid = n !== null && (!count || Number.isSafeInteger(n) && n >= 0);
  if (valid && measured !== null && Math.abs(n - measured) > tolerance) {notes.push(name + ': saved aggregate disagrees with samples; unavailable.'); return null;}
  if (valid) return n;
  if (saved !== undefined && saved !== null) {notes.push(name + ': invalid saved aggregate; unavailable.'); return null;}
  return measured;
 }
 const velocities = values('velocity'), clearances = values('wall_clearance');
 const collisionComplete = rows.length > 0 && rows.every(s => typeof s.wall_collision === 'boolean');
 const episodes = collisionComplete ? rows.filter((s, i) => s.wall_collision && (i === 0 || !rows[i - 1].wall_collision)).length : null;
 const contactSamples = collisionComplete ? rows.filter(s => s.wall_collision).length : null;
 return {id: scenario + ':' + revision, scenario, revision, recordedVerdict,
  independentVerdict: verdict(summary.independent_verification ?? independent.verification_execution),
  controllerSha256: hash(summary.controller_sha256), inventorySha256: inventory, samples, timeValid,
  minimumClearance: consistent('Minimum clearance', acceptance.minimum_measured_clearance_m, clearances ? Math.min(...clearances) : null),
  finalSpeed: finite(acceptance.final_speed_ms) !== null && Number(acceptance.final_speed_ms) < 0 ? null : consistent('Final speed', acceptance.final_speed_ms, velocities ? Math.abs(velocities.at(-1)!) : null),
  maximumSpeed: velocities ? Math.max(...velocities.map(Math.abs)) : null,
  contactEpisodes: consistent('Contact episodes', acceptance.wall_collision_events, episodes, true),
  contactSamples: consistent('Contact samples', acceptance.wall_contact_samples, contactSamples, true),
  firstTime: timeValid ? samples[0].time : null, lastTime: timeValid ? samples.at(-1)!.time : null,
  notes, recordedFailures: Array.isArray(acceptance.failure_reasons) ? acceptance.failure_reasons.filter((v): v is string => typeof v === 'string') : []};
}

export function parseStudy(responses: unknown[]): Study {
 if (responses.length !== scenarios.length) throw new Error('Three recorded scenario responses are required.');
 let inventorySha256 = '';
 const runs: RecordedRun[] = [];
 let defaults: Criteria | undefined;
 for (const [i, scenario] of scenarios.entries()) {
  const e = object(responses[i]), variants = object(e.variants), context = object(e.context);
  if (e.scenario !== scenario || !hash(e.inventory_sha256)) throw new Error('Recorded experiment identity is missing or differs.');
  if (inventorySha256 && inventorySha256 !== e.inventory_sha256) throw new Error('Mixed recording inventories are not comparable.');
  inventorySha256 = e.inventory_sha256 as string;
  const criteria = object(object(object(variants.original).summary).safety_acceptance).criteria;
  const c = object(criteria);
  const current = {minimumClearance: context.minimum_clearance_m, maximumFinalSpeed: context.max_final_speed_ms, maximumSettlingTime: context.completion_deadline_s, maximumContactEpisodes: c.wall_collision_events};
  if (validateCriteria(current).length) throw new Error('Original documented criteria are unavailable.');
  if (defaults && JSON.stringify(defaults) !== JSON.stringify(current)) throw new Error('This study has different per-scenario defaults; a common threshold set cannot be inferred.');
  defaults = current as Criteria;
  for (const revision of revisions) {
   if (!(revision in variants)) throw new Error('Recorded revision is missing: ' + scenario + '/' + revision);
   const run = extractRun(scenario, revision, variants[revision], inventorySha256);
   if (!run.controllerSha256) throw new Error('Recorded controller identity is unavailable.');
   const prior = runs.find(r => r.revision === revision);
   if (prior && prior.controllerSha256 !== run.controllerSha256) throw new Error('Controller identity changes across scenarios.');
   runs.push(run);
  }
 }
 return {runs, defaults: defaults!, inventorySha256};
}

/** Earliest saved sample whose entire remaining saved velocity suffix is below the chosen speed limit. */
export function settlingTime(run: RecordedRun, speedLimit: number): number | null {
 if (!run.timeValid || !run.samples.length || run.samples.some(s => s.velocity === null)) return null;
 let start: number | null = null;
 for (let i = run.samples.length - 1; i >= 0; i--) {
  if (Math.abs(run.samples[i].velocity!) >= speedLimit) break;
  start = run.samples[i].time;
 }
 return start;
}
export function evaluateRun(run: RecordedRun, criteria: Criteria): Evaluation {
 const errors = validateCriteria(criteria);
 if (errors.length) throw new Error(errors.join(' '));
 const settledAt = settlingTime(run, criteria.maximumFinalSpeed);
 const check = (criterion: Criterion, label: string, value: number | null, margin: number | null, unit: string, pass: boolean, rule: string): Check => ({criterion, label, value, margin, unit, status: value === null ? 'INSUFFICIENT_DATA' : pass ? 'PASS' : 'FAIL', explanation: value === null ? label + ': insufficient recorded data.' : rule});
 const checks = [
  check('clearance', 'Minimum clearance', run.minimumClearance, run.minimumClearance === null ? null : run.minimumClearance - criteria.minimumClearance, 'm', run.minimumClearance !== null && run.minimumClearance >= criteria.minimumClearance - tolerance, 'Measured clearance ≥ ' + criteria.minimumClearance + ' m (existing 1e−12 m tolerance).'),
  check('speed', 'Final absolute speed', run.finalSpeed, run.finalSpeed === null ? null : criteria.maximumFinalSpeed - run.finalSpeed, 'm/s', run.finalSpeed !== null && run.finalSpeed < criteria.maximumFinalSpeed, 'Final absolute speed must be strictly < ' + criteria.maximumFinalSpeed + ' m/s; equality fails.'),
  check('settling', 'Sampled settling time', settledAt, settledAt === null ? null : criteria.maximumSettlingTime - settledAt, 's', settledAt !== null && settledAt <= criteria.maximumSettlingTime + tolerance, 'Saved low-speed suffix begins by ' + criteria.maximumSettlingTime + ' s (1e−12 s tolerance).'),
  check('contacts', 'Wall contact episodes', run.contactEpisodes, run.contactEpisodes === null ? null : criteria.maximumContactEpisodes - run.contactEpisodes, 'episodes', run.contactEpisodes !== null && run.contactEpisodes <= criteria.maximumContactEpisodes, 'Contact episodes ≤ ' + criteria.maximumContactEpisodes + '; consecutive contact samples form one episode.')
 ];
 if (settledAt === null && run.timeValid && run.samples.length && run.samples.every(s => s.velocity !== null)) {
  const withinHorizon = run.lastTime !== null && run.lastTime >= criteria.maximumSettlingTime - tolerance;
  checks[2] = {...checks[2], status: withinHorizon ? 'FAIL' : 'INSUFFICIENT_DATA', explanation: withinHorizon ? 'No persistent sampled low-speed suffix was reached by the selected deadline.' : 'Settling was not observed; the selected deadline extends beyond the recorded horizon.'};
 }
 return {run, checks, settledAt, status: checks.some(c => c.status === 'FAIL') ? 'FAIL' : checks.some(c => c.status === 'INSUFFICIENT_DATA') ? 'INSUFFICIENT_DATA' : 'PASS'};
}

export function summarize(evaluations: Evaluation[], ranking: Criterion) {
 const eligible = evaluations.filter(e => e.checks.find(c => c.criterion === ranking)?.margin !== null);
 const min = eligible.length ? Math.min(...eligible.map(e => e.checks.find(c => c.criterion === ranking)!.margin!)) : null;
 const worst = min === null ? [] : eligible.filter(e => e.checks.find(c => c.criterion === ranking)!.margin === min);
 const observed = evaluations.filter(e => e.run.minimumClearance !== null);
 const failures = (['clearance', 'speed', 'settling', 'contacts'] as Criterion[]).map(criterion => ({criterion, count: evaluations.filter(e => e.checks.find(c => c.criterion === criterion)!.status === 'FAIL').length}));
 const mostFailures = Math.max(0, ...failures.map(x => x.count));
 return {passed: evaluations.filter(e => e.status === 'PASS').length, failed: evaluations.filter(e => e.status === 'FAIL').length, insufficient: evaluations.filter(e => e.status === 'INSUFFICIENT_DATA').length,
  worst, margin: min, ranked: eligible.length, worstClearance: observed.length ? Math.min(...observed.map(e => e.run.minimumClearance!)) : null,
  mostRestrictive: mostFailures ? failures.filter(x => x.count === mostFailures) : []};
}
export function revisionComparison(runs: RecordedRun[], criteria: Criteria) {
 return revisions.map(revision => {
  const selected = runs.filter(r => r.revision === revision), available = selected.filter(r => r.minimumClearance !== null);
  return {revision, runs: selected.length, passed: selected.filter(r => evaluateRun(r, criteria).status === 'PASS').length,
   worstClearance: available.length ? Math.min(...available.map(r => r.minimumClearance!)) : null};
 });
}

/** Null gaps stay gaps. Never interpolate, resample, normalize each run's time or extend its domain. */
export function recordedSeries(run: RecordedRun, signal: Signal): {time: number; value: number | null}[] {
 return run.timeValid ? run.samples.map(s => ({time: s.time, value: s[signal]})) : [];
}
export function displayNumber(v: number | null): string {
 if (v === null) return 'Unavailable';
 if (v !== 0 && Math.abs(v) < 1e-6) return v.toExponential(2);
 return Number(v.toPrecision(6)).toString();
}

import {describe, expect, it} from 'vitest';
import fixtureRaw from '../test/recorded-study.public.json?raw';
import {draftOf, evaluateRun, parseDraft, parseStudy, recordedSeries, revisionComparison, settlingTime, summarize, validateCriteria, type RecordedRun} from './physicsRegression';
const fixture = JSON.parse(fixtureRaw);
const responses = () => ['A', 'B', 'C'].map(s => structuredClone(fixture.experiments[s]));
const study = () => parseStudy(responses());

it('extracts the nine actual experiments, contact episodes and immutable verdicts', () => {
 const s = study();expect(s.runs).toHaveLength(9);
 const original = s.runs[0], first = s.runs[1], second = s.runs[2];
 expect(original.recordedVerdict).toBe('FAIL');expect(original.minimumClearance).toBeCloseTo(-0.0042, 12);expect(original.finalSpeed).toBeCloseTo(0.272105263157, 12);
 expect(original.contactEpisodes).toBe(1);expect(original.contactSamples).toBe(4);expect(first.contactEpisodes).toBe(0);expect(first.minimumClearance).toBeCloseTo(0.0249, 12);
 expect(second.recordedVerdict).toBe('PASS');expect(second.minimumClearance).toBeCloseTo(0.0524, 12);expect(second.maximumSpeed).toBeCloseTo(1.2, 12);
 expect(s.defaults).toEqual({minimumClearance: .05, maximumFinalSpeed: .03, maximumSettlingTime: 3, maximumContactEpisodes: 0});
 expect(s.runs.map(r => evaluateRun(r, s.defaults).status)).toEqual(['FAIL', 'FAIL', 'PASS', 'FAIL', 'FAIL', 'PASS', 'FAIL', 'FAIL', 'PASS']);
});
it('explains the first model repair as a clearance failure despite no contact and a low final speed', () => {
 const s = study(), e = evaluateRun(s.runs[1], s.defaults);
 expect(e.checks.filter(c => c.status === 'FAIL').map(c => c.criterion)).toEqual(['clearance']);
 expect(e.checks.find(c => c.criterion === 'clearance')!.margin).toBeCloseTo(-.0251, 12);
});
it('compares real revision minima and identifies the correct worst observed scenario', () => {
 const s = study(), comparison = revisionComparison(s.runs, s.defaults);
 expect(comparison.map(c => c.passed)).toEqual([0, 0, 3]);
 expect(comparison.map(c => c.worstClearance)).toEqual([s.runs[0].minimumClearance, s.runs[7].minimumClearance, s.runs[5].minimumClearance]);
 const all = summarize(s.runs.map(r => evaluateRun(r, s.defaults)), 'clearance');expect(all.worst.map(e => e.run.id)).toEqual(['A:original']);expect(all.mostRestrictive).toEqual([{criterion: 'clearance', count: 6}]);
 const repair = summarize(s.runs.filter(r => r.revision === 'attempt_2').map(r => evaluateRun(r, s.defaults)), 'clearance');expect(repair.worst.map(e => e.run.id)).toEqual(['B:attempt_2']);expect(repair.passed).toBe(3);
});
it('recalculates hypothetical results while preserving every source record and historical failure', () => {
 const raw = responses(), bytes = JSON.stringify(raw), s = parseStudy(raw), originalRuns = JSON.stringify(s.runs);
 expect(evaluateRun(s.runs[1], {...s.defaults, minimumClearance: .02}).status).toBe('PASS');
 expect(s.runs[1].recordedVerdict).toBe('FAIL');expect(JSON.stringify(s.runs)).toBe(originalRuns);expect(JSON.stringify(raw)).toBe(bytes);
});
it('applies inclusive clearance with the existing tolerance and strictly exclusive final speed', () => {
 const s = study(), run = s.runs[1];
 const equal = evaluateRun(run, {...s.defaults, minimumClearance: run.minimumClearance!, maximumFinalSpeed: run.finalSpeed!});
 expect(equal.checks[0].status).toBe('PASS');expect(equal.checks[1].status).toBe('FAIL');expect(equal.checks[1].margin).toBe(0);
 expect(evaluateRun(run, {...s.defaults, minimumClearance: run.minimumClearance! + 5e-13}).checks[0].status).toBe('PASS');
 expect(evaluateRun(run, {...s.defaults, minimumClearance: run.minimumClearance! + 2e-12}).checks[0].status).toBe('FAIL');
});
it('uses real timestamps for settling and supports deadline equality without claiming a zero-speed stop', () => {
 const s = study(), run = s.runs[2], time = settlingTime(run, .03)!;expect(time).toBeGreaterThan(1);expect(time).toBeLessThan(3);
 expect(evaluateRun(run, {...s.defaults, maximumSettlingTime: time}).checks[2].status).toBe('PASS');
 expect(evaluateRun(run, {...s.defaults, maximumSettlingTime: time - .005}).checks[2].status).toBe('FAIL');
 expect(settlingTime(s.runs[0], .03)).toBeNull();expect(evaluateRun(s.runs[0], s.defaults).checks[2].status).toBe('FAIL');
 expect(evaluateRun(s.runs[0], {...s.defaults, maximumSettlingTime: 4}).checks[2].status).toBe('INSUFFICIENT_DATA');
});
describe('invalid thresholds', () => {
 for (const bad of [NaN, Infinity, -Infinity, -1, true, null, '0.05']) it('rejects invalid clearance ' + String(bad), () => {
  const s = study();expect(validateCriteria({...s.defaults, minimumClearance: bad})).not.toHaveLength(0);
 });
 it('rejects zero speed, fractional contacts, unsafe integer counts and blank/overflow drafts', () => {
  const c = study().defaults;
  for (const bad of [{...c, maximumFinalSpeed: 0}, {...c, maximumContactEpisodes: .5}, {...c, maximumContactEpisodes: Number.MAX_SAFE_INTEGER + 1}]) expect(validateCriteria(bad).length).toBeGreaterThan(0);
  for (const text of ['', '1e999', 'Infinity']) expect(parseDraft({...draftOf(c), maximumFinalSpeed: text}).criteria).toBeNull();
  expect(parseDraft({...draftOf(c), minimumClearance: '0'}).criteria!.minimumClearance).toBe(0);
 });
});
it('treats missing metrics as unavailable and never converts null, booleans or nonfinite samples to zero', () => {
 const raw = responses(), t = raw[0].variants.attempt_2;
 delete t.summary.safety_acceptance.minimum_measured_clearance_m;t.samples.forEach((s: any) => delete s.wall_clearance);
 t.summary.safety_acceptance.final_speed_ms = null;t.samples.forEach((s: any) => {s.velocity = null;delete s.wall_collision;});
 delete t.summary.safety_acceptance.wall_collision_events;delete t.summary.safety_acceptance.wall_contact_samples;
 const s = parseStudy(raw), run = s.runs[2];expect(run.minimumClearance).toBeNull();expect(run.finalSpeed).toBeNull();expect(run.contactEpisodes).toBeNull();
 expect(evaluateRun(run, s.defaults).status).toBe('INSUFFICIENT_DATA');expect(run.recordedVerdict).toBe('PASS');
 const bad = responses();bad[0].variants.attempt_2.summary.safety_acceptance.final_speed_ms = -1;expect(parseStudy(bad).runs[2].finalSpeed).toBeNull();
});
it('withholds inconsistent aggregates and rejects mixed inventory, scenario, verdict or controller identity', () => {
 const raw = responses();raw[0].variants.attempt_2.summary.safety_acceptance.minimum_measured_clearance_m = 1;
 expect(parseStudy(raw).runs[2].minimumClearance).toBeNull();
 for (const alter of [(v: any[]) => v[1].inventory_sha256 = 'a'.repeat(64), (v: any[]) => v[0].scenario = 'C', (v: any[]) => v[0].variants.attempt_2.summary.safety_acceptance.status = 'FAIL', (v: any[]) => v[1].variants.attempt_2.summary.controller_sha256 = 'b'.repeat(64)]) {
  const value = responses();alter(value);expect(() => parseStudy(value)).toThrow();
 }
});
it('preserves each actual time domain and missing signal gaps without resampling', () => {
 const s = study(), run: RecordedRun = {...s.runs[0], samples: [{time: 2, position: 1, velocity: 2, wall_clearance: .4, wall_collision: false}, {time: 2.7, position: null, velocity: 1, wall_clearance: null, wall_collision: false}, {time: 4.1, position: 2, velocity: 0, wall_clearance: .1, wall_collision: false}]};
 expect(recordedSeries(run, 'position')).toEqual([{time: 2, value: 1}, {time: 2.7, value: null}, {time: 4.1, value: 2}]);
 const raw = responses();raw[0].variants.original.samples[1].time = 0;const invalid = parseStudy(raw).runs[0];expect(invalid.timeValid).toBe(false);expect(recordedSeries(invalid, 'velocity')).toEqual([]);
});
it('handles an empty selection without inventing a worst case or passing result', () => {
 const s = summarize([], 'clearance');expect(s.worst).toEqual([]);expect(s.margin).toBeNull();expect(s.worstClearance).toBeNull();expect(s.passed).toBe(0);
});

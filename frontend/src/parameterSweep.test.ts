import {expect, it} from 'vitest';
import raw from '../test/recorded-study.public.json?raw';
import {axisValues, compareReference, defaultAxis, exportPlan, historicalCellState, makePlan, parseAxis, parseSweepStudy, predict, summarizePlan, validatePhysical, type Axis, type PhysicalParameters} from './parameterSweep';
const evidence = JSON.parse(raw);
const responses = () => ['A', 'B', 'C'].map(s => structuredClone(evidence.experiments[s]));
const data = () => parseSweepStudy(responses());
const p: PhysicalParameters = {mass_kg: 2, speed_mps: 1.2, force_n: 4, gap_m: 1.77};
const axes = () => [parseAxis(defaultAxis('speed_mps')), parseAxis(defaultAxis('mass_kg'))];
const plan = () => {const d = data();return makePlan(d, 'A', 'attempt_2', p, axes(), d.study.defaults);};
it('generates a deterministic nine-case row-major grid with exact decimal increments', () => {
 const a = plan(), b = plan();expect(a).toEqual(b);expect(new Set(a.cases.map(c => c.id)).size).toBe(9);
 expect(a.cases.map(c => [c.parameters.mass_kg, c.parameters.speed_mps])).toEqual([[1,.4],[1,.8],[1,1.2],[2,.4],[2,.8],[2,1.2],[3,.4],[3,.8],[3,1.2]]);
 expect(a.cases.every(c => c.measured === null && c.execution_status === 'NOT_EXECUTED')).toBe(true);
});
it('includes only step-reachable endpoints and never creates floating-point duplicate cells', () => {
 expect(axisValues({parameter:'gap_m',minimum:.35,maximum:.7,step:.1})).toEqual([.35,.45,.55,.65]);
 expect(axisValues({parameter:'speed_mps',minimum:0,maximum:.3,step:.1})).toEqual([0,.1,.2,.3]);
 expect(axisValues({parameter:'mass_kg',minimum:2,maximum:2,step:1})).toEqual([2]);
});
it.each([NaN, Infinity, -Infinity, 0, -.1])('rejects invalid grid step %s', step => {
 expect(() => axisValues({parameter:'mass_kg',minimum:1,maximum:3,step})).toThrow();
});
it('rejects reversed ranges, unknown parameters and precision smaller than the supported increment', () => {
 expect(() => axisValues({parameter:'mass_kg',minimum:3,maximum:1,step:1})).toThrow();
 expect(() => axisValues({parameter:'mass_kg',minimum:1,maximum:3,step:.0000001})).toThrow('six decimal');
 expect(() => axisValues({parameter:'duration_s',minimum:1,maximum:3,step:1} as unknown as Axis)).toThrow('Unsupported');
});
it('enforces 25 before constructing a large grid; caps cannot raise the policy limit', () => {
 const d = data();const five = [{parameter:'mass_kg',minimum:1,maximum:3,step:.5},{parameter:'speed_mps',minimum:0,maximum:.8,step:.2}] as Axis[];
 expect(makePlan(d, 'A','original',p,five,d.study.defaults).cases).toHaveLength(25);
 expect(() => makePlan(d,'A','original',p,[{...five[0],maximum:4},five[1]],d.study.defaults)).toThrow('25');
 for (const cap of [0,26,Infinity,1.5]) expect(() => makePlan(d,'A','original',p,five,d.study.defaults,cap)).toThrow();
 expect(() => axisValues({parameter:'speed_mps',minimum:0,maximum:1.2,step:.000001})).toThrow('25');
});
it('allows a stricter cap and one-axis plans; rejects zero, duplicate or three axes', () => {
 const d=data();expect(makePlan(d,'A','original',p,axes().slice(0,1),d.study.defaults,3).cases).toHaveLength(3);
 expect(() => makePlan(d,'A','original',p,axes(),d.study.defaults,8)).toThrow();
 for (const a of [[],[axes()[0],axes()[0]],[...axes(),axes()[0]]]) expect(() => makePlan(d,'A','original',p,a,d.study.defaults)).toThrow('one or two distinct');
});
it.each([{mass_kg:0},{mass_kg:-1},{force_n:0},{force_n:-2},{force_n:Infinity},{speed_mps:1.21},{speed_mps:-1},{gap_m:.1},{gap_m:NaN},{mass_kg:true}])('rejects physically unsupported input %j', update => {
 expect(() => validatePhysical({...p,...update} as PhysicalParameters)).toThrow();
});
it('rejects extra physical fields and missing values', () => {
 expect(() => validatePhysical({...p,controller:'arbitrary.py'} as PhysicalParameters)).toThrow('Exactly four');
 const copy:any={...p};delete copy.force_n;expect(() => validatePhysical(copy)).toThrow();
});
it('matches independent hand calculations for a=2, d=.36, t=.6 and clearance=1.41', () => {
 const prediction=predict(p,data().study.defaults);
 expect(prediction.deceleration_mps2).toBe(2);expect(prediction.stopping_distance_m).toBeCloseTo(.36,14);expect(prediction.stopping_time_s).toBeCloseTo(.6,14);
 expect(prediction.remaining_clearance_m).toBeCloseTo(1.41,14);expect(prediction.clearance_margin_m).toBeCloseTo(1.36,14);expect(prediction.time_margin_s).toBeCloseTo(2.4,14);
 expect(prediction.kind).toBe('ANALYTICAL_PREDICTION');expect(prediction.classification).toBe('WITHIN_IDEAL_LIMITS');
});
it('supports stationary ideal cases without dividing by velocity; still requires positive force', () => {
 const prediction=predict({...p,speed_mps:0},data().study.defaults);expect(prediction.stopping_distance_m).toBe(0);expect(prediction.stopping_time_s).toBe(0);expect(prediction.remaining_clearance_m).toBe(1.77);
});
it('checks analytical inclusive clearance/time boundaries without claiming full measured acceptance', () => {
 const c=data().study.defaults;const at=predict(p,{...c,minimumClearance:1.41,maximumSettlingTime:.6});expect(at.classification).toBe('WITHIN_IDEAL_LIMITS');
 expect(predict(p,{...c,minimumClearance:1.410001}).classification).toBe('OUTSIDE_IDEAL_LIMITS');
 expect(predict(p,{...c,maximumSettlingTime:.599999}).classification).toBe('OUTSIDE_IDEAL_LIMITS');
 expect(() => predict(p,{...c,maximumFinalSpeed:0})).toThrow('positive');
});
it('summarizes ideal sampled boundaries without inventing observed boundaries', () => {
 const d=data(), a=makePlan(d,'A','original',{...p,gap_m:.35,force_n:2},axes(),d.study.defaults),s=summarizePlan(a);
 expect(s.predicted_within).toBe(4);expect(s.smallest_margin_m).toBeCloseTo(-.78,14);expect(s.predicted_transitions.length).toBeGreaterThan(0);expect(s.observed_transitions).toEqual([]);expect(s.executed).toBe(0);expect(s.worst_historical_clearance_m).toBeNull();
});
it('attaches only the exact anchor and never turns historical measurements into new case execution', () => {
 const a=plan();expect(a.cases.filter(c => c.savedReference)).toHaveLength(1);const c=a.cases[5];expect(c.savedReference!.scenario).toBe('A');
 expect(c.execution_status).toBe('NOT_EXECUTED');expect(c.measured).toBeNull();
 const comparison=compareReference(c,a.criteria)!;expect(comparison.recordedVerdict).toBe('PASS');expect(comparison.measured_minimum_clearance_m).toBeCloseTo(.0524,12);expect(comparison.clearance_minus_ideal_m).toBeCloseTo(-1.3576,12);
 expect(historicalCellState(a.cases[0],a.criteria)).toBe('INSUFFICIENT_DATA');expect(historicalCellState(c,a.criteria)).toBe('MEASURED_PASS');
});
it('preserves real original failure and reports analytical / measured disagreement without asserting its cause', () => {
 const d=data(), a=makePlan(d,'A','original',p,axes(),d.study.defaults),c=a.cases[5], r=compareReference(c,a.criteria)!;
 expect(r.recordedVerdict).toBe('FAIL');expect(r.evaluation.status).toBe('FAIL');expect(r.disagreement).toBe(true);expect(r.sampled_settling_time_s).toBeNull();expect(r.sampled_settling_travel_m).toBeNull();expect(r.travel_minus_ideal_m).toBeNull();expect(historicalCellState(c,a.criteria)).toBe('MEASURED_FAIL');
});
it('reuses the existing selected-criteria evaluator, preserving strict speed boundaries and source verdicts', () => {
 const d=data(), a=makePlan(d,'A','attempt_1',p,axes(),{...d.study.defaults,minimumClearance:.02}),c=a.cases[5];const r=compareReference(c,a.criteria)!;
 expect(r.recordedVerdict).toBe('FAIL');expect(r.evaluation.status).toBe('PASS');
 expect(compareReference(c,{...a.criteria,maximumFinalSpeed:c.savedReference!.run.finalSpeed!})!.evaluation.checks.find(x => x.criterion==='speed')!.status).toBe('FAIL');
});
it('withholds missing measured metrics rather than substituting analytical values or zero', () => {
 const copy=responses();for(const s of copy[0].variants.attempt_2.samples)delete s.wall_clearance;delete copy[0].variants.attempt_2.summary.safety_acceptance.minimum_measured_clearance_m;
 const d=parseSweepStudy(copy),a=makePlan(d,'A','attempt_2',p,axes(),d.study.defaults),r=compareReference(a.cases[5],a.criteria)!;
 expect(r.measured_minimum_clearance_m).toBeNull();expect(r.clearance_minus_ideal_m).toBeNull();expect(r.evaluation.status).toBe('INSUFFICIENT_DATA');expect(r.disagreement).toBeNull();expect(r.recordedVerdict).toBe('PASS');
});
it('rejects mismatched geometry / initial context and missing or mixed recording identities', () => {
 for(const change of [(c:any)=>c.context.wall_clearance=1.5,(c:any)=>c.context.joint_axis=[0,1,0],(c:any)=>c.variants.attempt_2.samples[0].velocity=.5,(c:any)=>c.inventory_sha256='f'.repeat(64)]){
  const copy=responses();change(copy[0]);expect(() => parseSweepStudy(copy)).toThrow();
 }
});
it('exports exact portable schema, null new measurements, labelled historical metrics and no arbitrary metadata', () => {
 const copy=responses();copy[0].context.extra_private_path='/private/example';const d=parseSweepStudy(copy),a=makePlan(d,'A','attempt_2',p,axes(),d.study.defaults);const before=JSON.stringify(a),payload=exportPlan(a),s=JSON.stringify(payload);
 expect(payload.format).toBe('EMBODY_RAIL_SWEEP_PLAN_V1');expect(payload.parameter_units.mass_kg).toBe('kg');expect(payload.execution_available).toBe(false);expect(payload.cases).toHaveLength(9);
 expect(payload.cases.every(c=>c.measured_results===null&&c.execution_status==='NOT_EXECUTED')).toBe(true);expect(payload.cases[5].historical_comparison!.kind).toBe('REUSED_SAVED_RECORDING_NOT_NEW_EXECUTION');expect(payload.cases[0].historical_comparison).toBeNull();
 expect(s).not.toContain('/private/');expect(s).not.toContain('NaN');expect(s).not.toContain('certificate');expect(JSON.stringify(a)).toBe(before);
});
it('never mutates actual fixture records, even when criteria and exported records are independently edited', () => {
 const copy=responses(),before=JSON.stringify(copy),d=parseSweepStudy(copy),a=makePlan(d,'A','attempt_2',p,axes(),d.study.defaults);
 predict(p,d.study.defaults);summarizePlan(a);exportPlan(a);expect(JSON.stringify(copy)).toBe(before);a.criteria.minimumClearance=.1;expect(d.study.defaults.minimumClearance).toBe(.05);
});
it('binds case identity to controller, anchor and numerical values; rebuilds stay reproducible', () => {
 const d=data(),a=plan(),b=makePlan(d,'A','original',p,axes(),d.study.defaults),c=makePlan(d,'B','attempt_2',p,axes(),d.study.defaults);
 expect(a.cases[0].id).not.toBe(b.cases[0].id);expect(a.cases[0].id).not.toBe(c.cases[0].id);expect(new Set(a.cases.map(c=>c.id)).size).toBe(9);
});

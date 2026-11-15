/** Bounded rail planning and saved-data comparison. No execution or write API. */
import {evaluateRun, finite, parseStudy, settlingTime, validateCriteria, type Criteria, type RecordedRun, type Scenario, type Study} from './physicsRegression';
import type {Variant} from './types';

export const MAX_CASES = 25;
export const parameters = {
 mass_kg: {label: 'Robot mass', unit: 'kg', low: 1, high: 4, mapping: 'BODYBASE.mass_kg'},
 speed_mps: {label: 'Initial velocity toward wall', unit: 'm/s', low: 0, high: 1.2, mapping: 'WORLDBASE.initial_velocity_ms'},
 force_n: {label: 'Maximum braking force', unit: 'N', low: 2, high: 6, mapping: 'BODYBASE.max_force_n'},
 gap_m: {label: 'Initial surface clearance', unit: 'm', low: .35, high: 2.2, mapping: 'Wall near face − initial bumper front'},
} as const;
export type Parameter = keyof typeof parameters;
export const parameterKeys = Object.keys(parameters) as Parameter[];
export type PhysicalParameters = Record<Parameter, number>;
export type Axis = {parameter: Parameter; minimum: number; maximum: number; step: number};
export type DraftAxis = {parameter: Parameter; minimum: string; maximum: string; step: string};
export type Prediction = {kind: 'ANALYTICAL_PREDICTION'; deceleration_mps2: number; stopping_distance_m: number; stopping_time_s: number; remaining_clearance_m: number; clearance_margin_m: number; time_margin_s: number; classification: 'WITHIN_IDEAL_LIMITS' | 'OUTSIDE_IDEAL_LIMITS'};
export type Reference = {scenario: Scenario; parameters: PhysicalParameters; context: Record<string, unknown>; run: RecordedRun};
export type SweepStudy = {study: Study; references: Reference[]};
export type SweepCase = {id: string; parameters: PhysicalParameters; prediction: Prediction; execution_status: 'NOT_EXECUTED'; measured: null; savedReference: Reference | null};
export type Plan = {schema_version: 1; model_id: 'rail_carriage'; controller_revision: Variant | 'reference'; controller_sha256: string; inventory_sha256: string; anchor_scenario: Scenario | null; initial_context: Record<string, unknown>; axes: Axis[]; fixed_parameters: PhysicalParameters; criteria: Criteria; cases: SweepCase[]};
export type CaseState = 'PLANNED' | 'PREDICTED' | 'NOT_EXECUTED' | 'RUNNING' | 'MEASURED_PASS' | 'MEASURED_FAIL' | 'EXECUTION_ERROR' | 'INSUFFICIENT_DATA';
export const stateLabels: Record<CaseState, string> = {PLANNED: 'Planned', PREDICTED: 'Analytical prediction', NOT_EXECUTED: 'Not executed', RUNNING: 'Running', MEASURED_PASS: 'Measured PASS', MEASURED_FAIL: 'Measured FAIL', EXECUTION_ERROR: 'Execution error', INSUFFICIENT_DATA: 'Insufficient data'};
export const limitations = [
 'Analytical prediction: ideal one-dimensional motion with constant maximum braking from t=0 until rest; no control delay, reverse acceleration, contact dynamics or numerical integration.',
 'Predicted clearance is initial signed surface gap minus ideal stopping distance. It is not the measured minimum clearance of the selected controller.',
 'Ideal time is exact rest under the ideal model. Measured settling is a sampled low-speed suffix, not exact rest; their definitions differ.',
 'This historical-controller plan grants no execution authority. A separate explicitly confirmed developer-reference sweep uses its own identities; historical repaired sources still require the qualified VM route, never host import.',
 'Only an exactly matching anchor can attach its saved recording. It remains historical evidence, not execution of a new grid case.',
 'Finite saved observations and ideal predictions do not certify real-world safety or a universal operating envelope.',
];
const scale = 1_000_000;
const obj = (v: unknown): Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {};
const eq = (a: number, b: number) => Math.abs(a - b) <= 1e-12;
function ticks(n: unknown, name: string): number {
 const x = finite(n);
 if (x === null || !Number.isSafeInteger(Math.round(x * scale)) || Math.abs(x * scale - Math.round(x * scale)) > 1e-7) throw new Error(name + ' must be finite with at most six decimal places.');
 return Math.round(x * scale);
}
export function validatePhysical(p: PhysicalParameters): void {
 if (Object.keys(p).length !== parameterKeys.length || Object.keys(p).some(k => !parameterKeys.includes(k as Parameter))) throw new Error('Exactly four supported physical parameters are required.');
 for (const key of parameterKeys) {
  const d = parameters[key];ticks(p[key], d.label);
  if (p[key] < d.low || p[key] > d.high) throw new Error(d.label + ' must be within ' + d.low + '–' + d.high + ' ' + d.unit + '.');
 }
}
export function axisValues(axis: Axis): number[] {
 if (!parameterKeys.includes(axis.parameter)) throw new Error('Unsupported sweep parameter.');
 const d = parameters[axis.parameter], low = ticks(axis.minimum, 'Minimum'), high = ticks(axis.maximum, 'Maximum'), step = ticks(axis.step, 'Step');
 if (axis.minimum < d.low || axis.maximum > d.high || low > high || step <= 0) throw new Error(d.label + ': ordered bounds within ' + d.low + '–' + d.high + ' ' + d.unit + ' and a positive step are required.');
 const count = Math.floor((high - low) / step) + 1;
 if (count > MAX_CASES) throw new Error('At most 25 experiment combinations are permitted.');
 return Array.from({length: count}, (_, i) => (low + i * step) / scale);
}
export function defaultAxis(parameter: Parameter): DraftAxis {
 const ranges = {mass_kg: ['1', '3', '1'], speed_mps: ['0.4', '1.2', '0.4'], force_n: ['2', '6', '2'], gap_m: ['0.35', '2.15', '0.9']};
 const [minimum, maximum, step] = ranges[parameter];return {parameter, minimum, maximum, step};
}
export function parseNumber(value: string): number {return value.trim() ? Number(value) : NaN;}
export function parseAxis(axis: DraftAxis): Axis {return {parameter: axis.parameter, minimum: parseNumber(axis.minimum), maximum: parseNumber(axis.maximum), step: parseNumber(axis.step)};}
export function predict(p: PhysicalParameters, criteria: Criteria): Prediction {
 validatePhysical(p);const errors = validateCriteria(criteria);if (errors.length) throw new Error(errors.join(' '));
 const a = p.force_n / p.mass_kg, distance = p.mass_kg * p.speed_mps ** 2 / (2 * p.force_n), time = p.mass_kg * p.speed_mps / p.force_n;
 const remaining = p.gap_m - distance, margin = remaining - criteria.minimumClearance, timeMargin = criteria.maximumSettlingTime - time;
 return {kind: 'ANALYTICAL_PREDICTION', deceleration_mps2: a, stopping_distance_m: distance, stopping_time_s: time, remaining_clearance_m: remaining, clearance_margin_m: margin, time_margin_s: timeMargin, classification: margin >= -1e-12 && timeMargin >= -1e-12 ? 'WITHIN_IDEAL_LIMITS' : 'OUTSIDE_IDEAL_LIMITS'};
}
export function parseSweepStudy(responses: unknown[]): SweepStudy {
 const study = parseStudy(responses), references: Reference[] = [];
 for (const [i, scenario] of (['A', 'B', 'C'] as const).entries()) {
  const c = obj(obj(responses[i]).context);
  const p = {mass_kg: c.mass_kg, speed_mps: c.initial_velocity_ms, force_n: c.braking_force_n, gap_m: c.wall_clearance} as PhysicalParameters;
  validatePhysical(p);
  if (c.robot_id !== 'linear_axis_01' || JSON.stringify(c.joint_axis) !== '[1,0,0]' || finite(c.bumper_front_x) === null || finite(c.wall_near_x) === null || !eq(Number(c.wall_near_x) - Number(c.bumper_front_x), p.gap_m)) throw new Error('Unsupported or inconsistent rail geometry context.');
  for (const key of ['wall_center_x_m', 'minimum_clearance_m', 'max_final_speed_ms', 'duration_s', 'timestep_s', 'completion_deadline_s']) if (finite(c[key]) === null || Number(c[key]) < 0) throw new Error('Invalid numeric rail context: ' + key);
  if (!Array.isArray(c.wall_half_size_m) || c.wall_half_size_m.length !== 3 || c.wall_half_size_m.some(v => finite(v) === null || v <= 0)) throw new Error('Invalid wall dimensions.');
  // Whitelist only public numerical metadata; never export arbitrary response fields.
  const context = Object.fromEntries(['robot_id', 'mass_kg', 'braking_force_n', 'initial_velocity_ms', 'wall_center_x_m', 'wall_half_size_m', 'joint_axis', 'minimum_clearance_m', 'max_final_speed_ms', 'duration_s', 'timestep_s', 'completion_deadline_s', 'bumper_front_x', 'wall_near_x', 'wall_clearance'].map(k => [k, c[k]]));
  for (const run of study.runs.filter(r => r.scenario === scenario)) {
   const first = run.samples[0];
   if (first && (first.velocity !== null && !eq(first.velocity, p.speed_mps) || first.wall_clearance !== null && !eq(first.wall_clearance, p.gap_m))) throw new Error('Saved initial samples disagree with physical context.');
   references.push({scenario, parameters: {...p}, context, run});
  }
 }
 return {study, references};
}
export function makePlan(data: SweepStudy, scenario: Scenario, revision: Variant, fixed: PhysicalParameters, axes: Axis[], criteria: Criteria, maxCases = MAX_CASES): Plan {
 validatePhysical(fixed);
 if (!Number.isSafeInteger(maxCases) || maxCases < 1 || maxCases > MAX_CASES) throw new Error('Case cap must be an integer from 1 to 25.');
 if (axes.length < 1 || axes.length > 2 || new Set(axes.map(a => a.parameter)).size !== axes.length) throw new Error('Select one or two distinct sweep parameters.');
 const reference = data.references.find(r => r.scenario === scenario && r.run.revision === revision);
 if (!reference) throw new Error('Recorded model/controller anchor unavailable.');
 const values = axes.map(axisValues);
 if (values.reduce((total, v) => total * v.length, 1) > maxCases) throw new Error('At most ' + maxCases + ' experiment combinations are permitted.');
 const cases: SweepCase[] = [];
 // Row-major: second (vertical) axis outer; first (horizontal) axis inner.
 for (const y of values[1] || [null]) for (const x of values[0]) {
  const p = {...fixed, [axes[0].parameter]: x};if (axes[1] && y !== null) p[axes[1].parameter] = y;
  const id = 'rail-v1:' + scenario + ':' + reference.run.controllerSha256 + ':' + parameterKeys.map(k => k + '=' + p[k]).join(';');
  const exactAnchor = parameterKeys.every(k => eq(p[k], reference.parameters[k]));
  cases.push({id, parameters: p, prediction: predict(p, criteria), execution_status: 'NOT_EXECUTED', measured: null, savedReference: exactAnchor ? reference : null});
 }
 return {schema_version: 1, model_id: 'rail_carriage', controller_revision: revision, controller_sha256: reference.run.controllerSha256, inventory_sha256: data.study.inventorySha256, anchor_scenario: scenario, initial_context: structuredClone(reference.context), axes: structuredClone(axes), fixed_parameters: {...fixed}, criteria: {...criteria}, cases};
}
export function compareReference(c: SweepCase, criteria: Criteria) {
 const run = c.savedReference?.run;
 if (!run) return null;
 const evaluation = evaluateRun(run, criteria), settled = settlingTime(run, criteria.maximumFinalSpeed);
 const first = run.samples[0], end = settled === null ? undefined : run.samples.find(s => s.time === settled);
 const measuredTravel = first?.position != null && end?.position != null ? end.position - first.position : null;
 return {recordedVerdict: run.recordedVerdict, evaluation, sampled_settling_time_s: settled, sampled_settling_travel_m: measuredTravel,
  travel_minus_ideal_m: measuredTravel === null ? null : measuredTravel - c.prediction.stopping_distance_m,
  measured_minimum_clearance_m: run.minimumClearance, clearance_minus_ideal_m: run.minimumClearance === null ? null : run.minimumClearance - c.prediction.remaining_clearance_m,
  disagreement: evaluation.status === 'INSUFFICIENT_DATA' ? null : (c.prediction.classification === 'WITHIN_IDEAL_LIMITS') !== (evaluation.status === 'PASS')};
}
export function summarizePlan(plan: Plan) {
 const smallest = Math.min(...plan.cases.map(c => c.prediction.clearance_margin_m));
 const references = plan.cases.flatMap(c => {const comparison = compareReference(c, plan.criteria);return comparison ? [{c, comparison}] : [];});
 const observed = references.flatMap(r => r.comparison.measured_minimum_clearance_m === null ? [] : [r.comparison.measured_minimum_clearance_m]);
 const transitions: {from: string; to: string; parameter: Parameter}[] = [];
 for (const axis of plan.axes) for (let i = 0; i < plan.cases.length; i++) for (let j = i + 1; j < plan.cases.length; j++) {
  const a = plan.cases[i], b = plan.cases[j];
  if (parameterKeys.some(k => k !== axis.parameter && a.parameters[k] !== b.parameters[k])) continue;
  const between = plan.cases.some(c => parameterKeys.every(k => k === axis.parameter || c.parameters[k] === a.parameters[k]) && c.parameters[axis.parameter] > a.parameters[axis.parameter] && c.parameters[axis.parameter] < b.parameters[axis.parameter]);
  if (!between && a.prediction.classification !== b.prediction.classification) transitions.push({from: a.id, to: b.id, parameter: axis.parameter});
 }
 return {smallest_margin_m: smallest, worst: plan.cases.filter(c => c.prediction.clearance_margin_m === smallest), predicted_within: plan.cases.filter(c => c.prediction.classification === 'WITHIN_IDEAL_LIMITS').length, executed: 0,
  historical_comparisons: references.length, historical_hypothetical_passes: references.filter(r => r.comparison.evaluation.status === 'PASS').length, disagreements: references.filter(r => r.comparison.disagreement === true).length,
  worst_historical_clearance_m: observed.length ? Math.min(...observed) : null, predicted_transitions: transitions, observed_transitions: []};
}
export function historicalCellState(c: SweepCase, criteria: Criteria): CaseState {
 const comparison = compareReference(c, criteria);
 return !comparison || comparison.evaluation.status === 'INSUFFICIENT_DATA' ? 'INSUFFICIENT_DATA' : comparison.evaluation.status === 'PASS' ? 'MEASURED_PASS' : 'MEASURED_FAIL';
}
/** Portable explicit download payload. Historical measurements never populate new execution fields. */
export function exportPlan(plan: Plan) {
 const reference=plan.controller_revision==='reference';
 return {format: reference?'EMBODY_REVIEWED_REFERENCE_PLAN_V1':'EMBODY_RAIL_SWEEP_PLAN_V1', schema_version: 1, execution_available: false, model_id: plan.model_id, controller_revision: plan.controller_revision, ...(reference?{trusted_source_sha256:plan.controller_sha256,designer_context_sha256:plan.inventory_sha256,registered_controller_id:plan.initial_context.controller_id}:{controller_sha256:plan.controller_sha256,recording_inventory_sha256:plan.inventory_sha256}),
  anchor_scenario: plan.anchor_scenario, initial_context: plan.initial_context, parameter_units: Object.fromEntries(parameterKeys.map(k => [k, parameters[k].unit])), criteria: plan.criteria,
  criteria_units: {minimumClearance: 'm', maximumFinalSpeed: 'm/s (exclusive)', maximumSettlingTime: 's', maximumContactEpisodes: 'episodes'}, axes: plan.axes, fixed_parameters: plan.fixed_parameters,
  cases: plan.cases.map(c => {const ref = compareReference(c, plan.criteria);return {experiment_id: c.id, parameters: c.parameters, analytical_prediction: c.prediction, execution_status: c.execution_status, measured_results: null,
   historical_comparison: ref ? {kind: 'REUSED_SAVED_RECORDING_NOT_NEW_EXECUTION', scenario: c.savedReference!.scenario, controller_sha256: c.savedReference!.run.controllerSha256, inventory_sha256: plan.inventory_sha256, recorded_verdict: ref.recordedVerdict, derived_status: ref.evaluation.status, minimum_clearance_m: ref.measured_minimum_clearance_m, sampled_settling_time_s: ref.sampled_settling_time_s, sampled_settling_travel_m: ref.sampled_settling_travel_m, clearance_minus_ideal_m: ref.clearance_minus_ideal_m, travel_minus_ideal_m: ref.travel_minus_ideal_m} : null};}), limitations};
}

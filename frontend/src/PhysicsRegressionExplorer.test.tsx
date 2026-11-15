import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, expect, it, vi} from 'vitest';
import raw from '../test/recorded-study.public.json?raw';
import unifiedRaw from '../test/unified.json?raw';
import engineeringRaw from '../test/engineering.json?raw';
import PhysicsRegressionExplorer from './PhysicsRegressionExplorer';
import RecordedTrajectoryPlot from './RecordedTrajectoryPlot';
import UnifiedWorkspace from './UnifiedWorkspace';
import App from './App';
import {parseStudy} from './physicsRegression';
const evidence = JSON.parse(raw), rover = JSON.parse(unifiedRaw), engineering = JSON.parse(engineeringRaw);
const {webcrypto} = await vi.importActual<{webcrypto: Crypto}>('node:crypto');
const {TextEncoder: NodeTextEncoder} = await vi.importActual<{TextEncoder: typeof TextEncoder}>('node:util');
vi.mock('./Editor', () => ({default: () => <div>Existing editor DOM fixture</div>}));
vi.mock('./Viewport', () => ({default: () => <div>Existing rail viewport DOM fixture</div>}));
vi.mock('./WorldViewport', () => ({default: () => <div>DOM-only existing viewport fixture</div>}));
let requests: {path: string; options: unknown}[];
beforeEach(() => {
 localStorage.clear();requests = [];
 vi.stubGlobal('TextEncoder', NodeTextEncoder);vi.stubGlobal('crypto', webcrypto);
 vi.stubGlobal('fetch', vi.fn(async (path: string, options?: unknown) => {
  requests.push({path, options});const u = new URL(path, 'http://127.0.0.1');let data;
  if (u.pathname === '/api/bootstrap') data = evidence.bootstrap;
  else if (u.pathname === '/api/agent/recorded') data = evidence.agent;
  else if (u.pathname === '/api/experiment') data = evidence.experiments[u.searchParams.get('scenario')!];
  else if (u.pathname === '/api/proposal') data = evidence.proposals[u.searchParams.get('variant')!];
  else if (u.pathname === '/api/file') data = evidence.files[u.searchParams.get('path')!];
  else if (u.pathname === '/api/workspace') data = {...rover, snapshot: {...rover.snapshot, key: 'current', project: engineering.project, project_sha256: engineering.identities.project, historical: false, editable: true, runs: [], proposals: [], shape_parts: []}};
  else throw new Error('Unexpected test request: ' + path);
  return {ok: true, json: async () => structuredClone(data)};
 }));
});
async function open() {render(<PhysicsRegressionExplorer/>);await screen.findByRole('table');}
it('loads all actual runs and updates hypothetical results while preserving recorded verdicts', async () => {
 await open();expect(screen.getByLabelText('Derived engineering summary')).toHaveTextContent('3 / 9');
 const cell = screen.getByRole('button', {name: 'Inspect scenario A · First repair'});expect(cell).toHaveTextContent('Recorded FAIL');expect(cell).toHaveTextContent('Hypothetical FAIL');
 fireEvent.change(screen.getByLabelText('Minimum wall clearance'), {target: {value: '.02'}});
 expect(cell).toHaveTextContent('Recorded FAIL');expect(cell).toHaveTextContent('Hypothetical PASS');expect(screen.getByLabelText('Derived engineering summary')).toHaveTextContent('6 / 9');
 fireEvent.click(screen.getByRole('button', {name: 'Reset to recorded criteria'}));expect(cell).toHaveTextContent('Hypothetical FAIL');
 expect(requests).toHaveLength(3);expect(requests.every(r => r.options === undefined)).toBe(true);
});
it('filters scenarios/revisions, inspects physical failure and ranks the second repair correctly', async () => {
 await open();fireEvent.click(screen.getByRole('button', {name: 'Inspect scenario A · Original controller'}));
 expect(screen.getByLabelText('Selected run details')).toHaveTextContent('No persistent sampled low-speed suffix');
 const filter = screen.getByRole('group', {name: 'Controller revisions'});fireEvent.click(within(filter).getByLabelText('Original controller'));fireEvent.click(within(filter).getByLabelText('First repair'));
 expect(screen.getByLabelText('Worst recorded cases')).toHaveTextContent('B · Second repair');
 fireEvent.click(screen.getByLabelText('Scenario B'));expect(screen.getByRole('table')).not.toHaveTextContent('Scenario B');
 fireEvent.click(screen.getByLabelText('Scenario A'));fireEvent.click(screen.getByLabelText('Scenario C'));expect(screen.getByRole('status')).toHaveTextContent('Select at least one');
});
it('withholds invalid derived results without hiding immutable recorded results', async () => {
 await open();fireEvent.change(screen.getByLabelText('Maximum final speed (exclusive)'), {target: {value: '0'}});
 expect(screen.getByRole('alert')).toHaveTextContent('finite positive');const cell = screen.getByRole('button', {name: 'Inspect scenario A · Second repair'});expect(cell).toHaveTextContent('Recorded PASS');expect(cell).toHaveTextContent('Hypothetical Withheld');
 fireEvent.change(screen.getByLabelText('Maximum wall contact episodes'), {target: {value: '.5'}});expect(screen.getByRole('alert')).toHaveTextContent('safe integer');
});
it('changes overlays/signals and seeks actual saved timestamps', async () => {
 await open();expect(screen.getAllByTestId(/^trajectory-/)).toHaveLength(3);
 const overlays = screen.getByRole('group', {name: 'Trajectory overlays'});fireEvent.click(within(overlays).getByLabelText('A · Original controller'));expect(screen.queryByTestId('trajectory-A:original')).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Trajectory signal'), {target: {value: 'velocity'}});expect(screen.getByRole('img')).toHaveAccessibleName('Velocity compared over actual recorded time');
 fireEvent.change(screen.getByRole('slider', {name: 'Recorded trajectory timestamp'}), {target: {value: '200'}});expect(screen.getByLabelText('Recorded trajectory comparison')).toHaveTextContent('1 s');
});
it('reads checksum-matched saved controller diffs through GET only', async () => {
 await open();fireEvent.click(screen.getByText('Inspect saved controller revision'));fireEvent.click(screen.getByRole('button', {name: 'Load saved source'}));
 expect(await screen.findByLabelText('Saved controller source')).toHaveTextContent('HOLDING_EXTRA_CLEARANCE_M');
 fireEvent.click(screen.getByLabelText('Show recorded diff from original'));expect(screen.getByLabelText('Saved controller source')).toHaveTextContent('def faulty_braking_controller');
 expect(requests.every(r => r.options === undefined)).toBe(true);
});
it('rejects altered controller text instead of silently presenting it as this run', async () => {
 await open();const original = vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation(async (...args) => args[0].toString().includes('/api/proposal') ? {ok: true, json: async () => ({...evidence.proposals.attempt_2, source: 'altered'})} as Response : original(...args));
 fireEvent.click(screen.getByText('Inspect saved controller revision'));fireEvent.click(screen.getByRole('button', {name: 'Load saved source'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('source differs');expect(screen.queryByLabelText('Saved controller source')).not.toBeInTheDocument();
});
it('provides loading/error/retry states and never substitutes fixture success for unavailable data', async () => {
 vi.mocked(fetch).mockResolvedValue({ok: false, json: async () => ({error: 'Evidence hash mismatch'})} as Response);
 render(<PhysicsRegressionExplorer/>);expect(screen.getByRole('status')).toHaveTextContent('Loading');expect(await screen.findByRole('alert')).toHaveTextContent('Evidence hash mismatch');expect(screen.queryByRole('table')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button', {name: 'Retry saved-data read'}));await waitFor(() => expect(fetch).toHaveBeenCalledTimes(6));
});
it('ignores older async study responses after retry/unmount', async () => {
 const original = vi.mocked(fetch).getMockImplementation()!;let resolve: (value: Response) => void = () => {};
 vi.mocked(fetch).mockImplementationOnce(() => new Promise<Response>(r => {resolve = r;}));const view = render(<PhysicsRegressionExplorer/>);view.unmount();
 await act(async () => resolve(await original('/api/experiment?scenario=A') as Response));expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
it('renders missing data honestly and keeps gaps and different recorded time domains', async () => {
 const study = parseStudy(['A', 'B', 'C'].map(s => evidence.experiments[s]));const run = {...study.runs[0], samples: [{time: 2, position: 1, velocity: 1, wall_clearance: .1, wall_collision: false}, {time: 4, position: null, velocity: 0, wall_clearance: null, wall_collision: false}, {time: 5, position: 2, velocity: 0, wall_clearance: .05, wall_collision: false}]};
 render(<RecordedTrajectoryPlot runs={[run]} criteria={study.defaults}/>);const line = screen.getByTestId('trajectory-A:original');expect(line).toHaveAttribute('data-start', '2');expect(line).toHaveAttribute('data-end', '5');expect(line.getAttribute('d')!.match(/M/g)).toHaveLength(2);expect(line.getAttribute('d')).not.toContain('NaN');
});
it('mounts the entry point in actual workbench verification without execution or application', async () => {
 const onOpen = vi.fn();render(<UnifiedWorkspace onOpenPhysicsRegression={onOpen}/>);await screen.findByTestId('unified-project-identity');fireEvent.click(screen.getByRole('button', {name: 'Simulate'}));fireEvent.click(screen.getByRole('button', {name: 'Open Physics Regression Explorer'}));expect(onOpen).toHaveBeenCalledOnce();expect(requests.every(r => r.options === undefined)).toBe(true);
});

it('shows unavailable metrics without zero substitution and retains the recorded PASS', async () => {
 const copy = structuredClone(evidence.experiments);const t = copy.A.variants.attempt_2;delete t.summary.safety_acceptance.minimum_measured_clearance_m;t.samples.forEach((s: any) => delete s.wall_clearance);
 vi.mocked(fetch).mockImplementation(async (path) => ({ok: true, json: async () => copy[new URL(String(path), 'http://127.0.0.1').searchParams.get('scenario')!]} as Response));
 render(<PhysicsRegressionExplorer/>);await screen.findByRole('table');const cell = screen.getByRole('button', {name: 'Inspect scenario A · Second repair'});expect(cell).toHaveTextContent('Recorded PASS');expect(cell).toHaveTextContent('Hypothetical Insufficient data');expect(cell).toHaveTextContent('Min gap Unavailable');
});

it('opens the actual explorer from App verification and returns to the existing project', async () => {
 render(<App/>);await screen.findByTestId('unified-project-identity');fireEvent.click(screen.getByRole('button', {name: 'Simulate'}));fireEvent.click(screen.getByRole('button', {name: 'Open Physics Regression Explorer'}));await screen.findByRole('table');expect(screen.getByRole('region', {name: 'Physics Regression Explorer'}).closest('.ide')).toHaveClass('regression-mode');fireEvent.click(screen.getByRole('button', {name: 'Back to workbench'}));expect(screen.getByTestId('unified-project-identity')).toHaveAttribute('data-project', engineering.project.id);expect(requests.every(r => r.options === undefined)).toBe(true);
});

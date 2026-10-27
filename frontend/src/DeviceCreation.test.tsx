import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import raw from '../test/day16_creation.json?raw';
import DeviceCreation from './DeviceCreation';
const {call}=vi.hoisted(()=>({call:vi.fn()}));vi.mock('./api',()=>({api:(...args:unknown[])=>call(...args)}));
const fixtures=JSON.parse(raw);
beforeEach(()=>{call.mockReset();call.mockImplementation(async(path:string)=>{if(path==='creation/capabilities')return {projects:[]};if(path==='creation/plan')return structuredClone(fixtures.barrier);if(path==='creation/decide')return {project:fixtures.barrier.proposed_project};throw new Error('Unexpected DOM fixture call');});});
it('shows actual construction data and requires explicit checked build, with no automatic application',async()=>{
 const created=vi.fn().mockResolvedValue(undefined);render(<DeviceCreation onClose={vi.fn()} onCreated={created}/>);
 fireEvent.click(screen.getByRole('button',{name:'Create engineering plan'}));await screen.findByTestId('creation-project-id');
 expect(screen.getByText('7 editable physical objects')).toBeInTheDocument();expect(screen.getByText('6 catalog components · 12 graph connections')).toBeInTheDocument();expect(call.mock.calls.some(c=>c[0]==='creation/decide')).toBe(false);
 expect(screen.getByRole('button',{name:'Build supported project'})).toBeDisabled();fireEvent.click(screen.getByRole('checkbox',{name:'Approve supported project creation'}));fireEvent.click(screen.getByRole('button',{name:'Build supported project'}));
 await waitFor(()=>expect(created).toHaveBeenCalledWith(fixtures.barrier.proposed_project));expect(call).toHaveBeenCalledWith('creation/decide',expect.objectContaining({expected_sha256:fixtures.barrier.base_sha256,expected_revision:0,decision:'build',confirmation:'BUILD REVIEWED SUPPORTED PROJECT'}));
});
it('rejects a reviewed creation without invoking the created callback',async()=>{
 const close=vi.fn(),created=vi.fn();render(<DeviceCreation onClose={close} onCreated={created}/>);fireEvent.click(screen.getByRole('button',{name:'Create engineering plan'}));await screen.findByTestId('creation-project-id');fireEvent.click(screen.getByRole('button',{name:'Reject creation'}));await waitFor(()=>expect(close).toHaveBeenCalled());expect(created).not.toHaveBeenCalled();expect(call).toHaveBeenCalledWith('creation/decide',expect.objectContaining({decision:'reject',confirmation:'REJECT DEVICE CREATION'}));
});
it('presents glasses as fourteen editable envelopes with no active electronic parts',async()=>{
 call.mockImplementation(async(path:string)=>path==='creation/capabilities'?{projects:[]}:structuredClone(fixtures.glasses));render(<DeviceCreation onClose={vi.fn()} onCreated={vi.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Smart glasses concept'}));fireEvent.click(screen.getByRole('button',{name:'Create engineering plan'}));await screen.findByTestId('creation-project-id');expect(screen.getByText('14 editable physical objects')).toBeInTheDocument();expect(screen.getByText('0 catalog components · 0 graph connections')).toBeInTheDocument();expect(screen.getByText(/No active electronics or controller/)).toBeInTheDocument();
});
it('keeps errors visible without fabricating a built project on failed planning',async()=>{
 call.mockImplementation(async(path:string)=>{if(path==='creation/capabilities')return {projects:[]};throw new Error('Unsupported family or stale base');});const created=vi.fn();render(<DeviceCreation onClose={vi.fn()} onCreated={created}/>);fireEvent.click(screen.getByRole('button',{name:'Create engineering plan'}));await screen.findByRole('alert');expect(created).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'Build supported project'})).not.toBeInTheDocument();
});

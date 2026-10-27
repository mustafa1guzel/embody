import {expect,it,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import raw from '../test/robustness.json?raw';
import RobustnessPanel from './RobustnessPanel';
const actualOffline=JSON.parse(raw);
it('shows actual frozen compiled models without inventing candidate results or launch actions',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>actualOffline}));vi.stubGlobal('fetch',fetch);
 render(<RobustnessPanel/>);await screen.findByText(/NOT_RUN_AWAITING_FRESH_VM_APPROVAL/);
 expect(screen.getByText(/0 new measured pairs/)).toBeInTheDocument();
 expect(screen.getAllByRole('row')).toHaveLength(41);
 fireEvent.change(screen.getByRole('combobox',{name:'Robustness family'}),{target:{value:'arm'}});
 expect(screen.getAllByRole('row')).toHaveLength(41);
 expect(screen.getAllByText('CONDITIONALLY_FEASIBLE')).toHaveLength(40);
 expect(fetch).toHaveBeenCalledWith('/api/robustness',undefined);
 expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
it('blocks visibly on stale frozen implementation instead of substitute evidence',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>({error:'Benchmark implementation/source/configuration is stale'})})));
 render(<RobustnessPanel/>);expect(await screen.findByRole('alert')).toHaveTextContent('stale');
 expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

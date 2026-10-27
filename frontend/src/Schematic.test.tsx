import {expect,it,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import raw from '../test/hardware.json?raw';
import Schematic from './Schematic';
it('uses authoritative wire IDs, selects real endpoints and emits exact typed edits',()=>{
 const f=JSON.parse(raw),assembly=f.bootstrap.template,edit=vi.fn(async()=>{}),select=vi.fn();
 const view=render(<Schematic assembly={assembly} catalog={f.bootstrap.catalog} onEdit={edit} onSelect={select}/>);
 expect(view.container.querySelectorAll('path[data-wire-id]')).toHaveLength(assembly.wires.length);
 fireEvent.click(screen.getByRole('button',{name:'Schematic pin sensor.ECHO'}));fireEvent.click(screen.getByRole('button',{name:'Schematic pin board.IO19'}));fireEvent.click(screen.getByText('Connect schematic pins'));
 expect(edit).toHaveBeenCalledWith([{kind:'connect_pins',a:{component:'sensor',pin:'ECHO'},b:{component:'board',pin:'IO19'}}]);
 const wire=assembly.wires[0];fireEvent.click(screen.getByRole('button',{name:'Disconnect schematic '+wire.id}));expect(edit).toHaveBeenLastCalledWith([{kind:'disconnect_pins',wire_id:wire.id}]);
 expect(select).toHaveBeenCalledWith('sensor');
});

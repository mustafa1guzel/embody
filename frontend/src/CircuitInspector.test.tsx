import {expect,it,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import raw from '../test/hardware.json?raw';
import CircuitInspector from './CircuitInspector';
const f=JSON.parse(raw);
it('shows exact selected pin metadata and peers, keeping UNKNOWN distinct and connection explicit',()=>{
 const begin=vi.fn(),select=vi.fn(),disconnect=vi.fn();
 render(<CircuitInspector selection={{kind:'pin',endpoint:{component:'sensor',pin:'ECHO'}}} assembly={f.bootstrap.template} catalog={f.bootstrap.catalog} diagnostics={f.diagnostics} onSelect={select} onBegin={begin} onDisconnect={disconnect} busy={false}/>);
 expect(screen.getByTestId('selected-pin-id')).toHaveTextContent('sensor.ECHO');expect(screen.getByText('4.75 – 5.25 V')).toBeInTheDocument();expect(screen.getByText('UNKNOWN',{exact:true})).toBeInTheDocument();expect(begin).not.toHaveBeenCalled();expect(disconnect).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Begin connection'}));expect(begin).toHaveBeenCalledWith({component:'sensor',pin:'ECHO'});
});
it('inspects actual graph edge and net and disconnects only on a gesture',()=>{
 const wire=f.bootstrap.template.wires[0],disconnect=vi.fn();
 render(<CircuitInspector selection={{kind:'wire',wireId:wire.id}} assembly={f.bootstrap.template} catalog={f.bootstrap.catalog} diagnostics={f.diagnostics} onSelect={vi.fn()} onBegin={vi.fn()} onDisconnect={disconnect} busy={false}/>);
 expect(screen.getByTestId('selected-net')).toHaveTextContent(wire.net);expect(disconnect).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Disconnect selected wire'}));expect(disconnect).toHaveBeenCalledWith(wire.id);
});

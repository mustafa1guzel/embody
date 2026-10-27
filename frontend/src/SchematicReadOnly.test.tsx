import {expect,it,vi} from 'vitest';import {render,screen,fireEvent} from '@testing-library/react';
import raw from '../test/engineering.json?raw';import Schematic from './Schematic';
it('uses the actual graph and catalog for inspection, with connection/disconnection disabled',()=>{
 const b=JSON.parse(raw),edit=vi.fn(),select=vi.fn();render(<Schematic assembly={b.project.circuit} catalog={b.catalog} onEdit={edit} onSelect={select} readOnly/>);
 const c=b.project.circuit.components[0];fireEvent.click(screen.getByRole('button',{name:'Schematic component '+c.id}));expect(select).toHaveBeenCalledWith(c.id);
 expect(screen.getByRole('button',{name:'Connect schematic pins'})).toBeDisabled();for(const b of screen.getAllByRole('button',{name:/Disconnect schematic/}))expect(b).toBeDisabled();expect(edit).not.toHaveBeenCalled();
 expect(screen.getByRole('img',{name:'Authoritative circuit schematic'})).toBeInTheDocument();
});

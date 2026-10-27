import {expect,it,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import raw from '../test/hardware.json?raw';
import HardwareViewport,{endpointPosition} from './HardwareViewport';

const {draw}=vi.hoisted(()=>({draw:vi.fn()}));
vi.mock('three',async original=>{
 const actual=await original<typeof import('three')>();
 return {...actual,WebGLRenderer:class {
  domElement=document.createElement('canvas');
  setClearColor(){} setPixelRatio(){} setSize(){} dispose(){} render=draw;
 }};
});
it('redraws the real transform controls immediately when mode changes',()=>{
 const fixture=JSON.parse(raw),props={assembly:fixture.bootstrap.template,catalog:fixture.bootstrap.catalog,selection:'sensor',onSelect:vi.fn(),onTransform:vi.fn(),snap:true,visible:true};
 const view=render(<HardwareViewport {...props} mode="translate"/>);
 const before=draw.mock.calls.length;
 view.rerender(<HardwareViewport {...props} mode="rotate"/>);
 expect(draw.mock.calls.length).toBeGreaterThan(before);
 const scene=draw.mock.calls.at(-1)![0];
 const helper=scene.children.find((child:any)=>child.isTransformControlsRoot);
 expect(helper.children.find((child:any)=>child.isTransformControlsGizmo).mode).toBe('rotate');
 view.unmount();
});

it('selects an exact projected catalog pin without invoking a transform',()=>{
 const fixture=JSON.parse(raw),interaction=vi.fn(),transform=vi.fn();
 const v=render(<HardwareViewport assembly={fixture.bootstrap.template} catalog={fixture.bootstrap.catalog} selection="sensor" onSelect={vi.fn()} onTransform={transform} mode="translate" snap visible onInteraction={interaction}/>);
 fireEvent.click(screen.getByRole('button',{name:'Pin sensor.ECHO'}));expect(interaction).toHaveBeenCalledWith({kind:'pin',endpoint:{component:'sensor',pin:'ECHO'}});expect(transform).not.toHaveBeenCalled();v.unmount();
});

it('snaps a dashed uncommitted preview to both exact catalog anchors',()=>{
 const fixture=JSON.parse(raw),source={component:'sensor',pin:'ECHO'},target={component:'board',pin:'IO19'};
 const v=render(<HardwareViewport assembly={fixture.bootstrap.template} catalog={fixture.bootstrap.catalog} selection="sensor" onSelect={vi.fn()} onTransform={vi.fn()} mode="translate" snap visible connecting={source} interaction={{kind:'pin',endpoint:target}}/>);
 const scene=draw.mock.calls.at(-1)![0],draft=scene.children.find((o:any)=>o.isLine&&o.material.isLineDashedMaterial);expect(draft).toBeDefined();
 const points=draft.geometry.attributes.position;expect(points.count).toBe(33);const p=endpointPosition(fixture.bootstrap.template,fixture.bootstrap.catalog,target);p.forEach((value:number,i:number)=>expect(points.array[(points.count-1)*3+i]).toBeCloseTo(value,7));v.unmount();
});

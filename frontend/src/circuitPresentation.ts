import type {Assembly,Electrical,Part,Wire} from './hardwareTypes';
export function diagnosticNets(assembly:Assembly,diagnostics?:Electrical|null):Set<string>{
 const nets=new Set<string>();
 for(const diagnostic of diagnostics?.diagnostics||[]){if(diagnostic.severity!=='ERROR')continue;
  for(const reference of diagnostic.references||[]){
   if(typeof reference==='string'&&assembly.nets.some(n=>n.id===reference))nets.add(reference);
   if(Array.isArray(reference)&&reference.length===2)for(const w of assembly.wires)if([w.a,w.b].some(e=>e.component===reference[0]&&e.pin===reference[1]))nets.add(w.net);
  }
 }
 return nets;
}
export function signalCategory(a:Assembly,catalog:Record<string,Part>,wire:Wire):string{
 const endpoints=a.wires.filter(w=>w.net===wire.net).flatMap(w=>[w.a,w.b]);
 const roles=endpoints.map(e=>{const c=a.components.find(c=>c.id===e.component)!;return c.roles[e.pin]||catalog[c.part].pins.find(p=>p.id===e.pin)!.role;});
 return roles.includes('ground')?'Ground reference':roles.some(r=>r.startsWith('power'))?'Power':roles.some(r=>['input','output','pwm'].includes(r))?'Signal':'Category UNKNOWN';
}

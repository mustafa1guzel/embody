"""Supported static diagnostics. No transient, thermal or full circuit simulation."""
from .assemblies import validate, netlist, identity
from .library import CATALOG, pin
from physics.contracts import digest


def inspect(a):
    validate(a);nets=netlist(a);components={c['id']:c for c in a['components']};membership={e:n for n,ends in nets.items() for e in ends}
    diagnostics=[];calculations=[]
    def issue(code,severity,message,refs=()):
        diagnostics.append({'code':code,'severity':severity,'message':message,'references':list(refs)})
    def role(e):
        c=components[e[0]];p=pin(c['part'],e[1]);return c['roles'].get(e[1],p.role)
    grounds={membership[(c['id'],p.id)] for c in components.values() for p in CATALOG[c['part']].pins if p.role=='ground' and (c['id'],p.id) in membership}
    if len(grounds)>1:issue('COMMON_GROUND','ERROR','Ground pins do not share one explicit reference net.',sorted(grounds))
    for c in components.values():
        spec=CATALOG[c['part']]
        for p in spec.pins:
            e=(c['id'],p.id);n=membership.get(e)
            if p.required and not n:issue('REQUIRED_PIN','ERROR',f'{c["name"]}.{p.id} is unconnected.',[list(e)])
            if p.role=='configurable' and p.id in c['roles'] and c['roles'][p.id] not in p.capabilities:
                issue('GPIO_CAPABILITY','ERROR',f'{p.id} cannot provide {c["roles"][p.id]}.',[list(e)])
            if n and p.role=='configurable' and p.id not in c['roles']:issue('GPIO_ROLE','UNKNOWN',f'Configure the direction of {c["name"]}.{p.id}.',[list(e)])
        if spec.kind in ('servo','supply','board'):
            issue('CURRENT_MARGIN','UNKNOWN',f'{c["name"]}: worst-case load or supply capability is unavailable; current margin is UNKNOWN.',[c['id']])
    # Net source voltages. Ground/power clashes are errors even without a load.
    voltages={};drivers={}
    for n,ends in nets.items():
        active=[e for e in ends if role(e) in ('power_out','output','pwm')];drivers[n]=active
        if len(active)>1:issue('OUTPUT_CONFLICT','ERROR','Multiple active drivers share a net.',[n])
        if active:
            e=active[0];c=components[e[0]];p=pin(c['part'],e[1]);v=CATALOG[c['part']].properties.get('output_high_v') if p.role=='configurable' else p.voltage_v
            if v is not None:voltages[n]=list(v)
        if any(role(e)=='ground' for e in ends):
            if active:issue('SUPPLY_GROUND_CONFLICT','ERROR','Driven output is shorted to a ground reference.',[n])
            voltages[n]=[0.,0.]
        if any(role(e)=='power_in' for e in ends):
            if not active or not all(role(e)=='power_out' for e in active):
                issue('MISSING_POWER','ERROR','Power inputs require an explicit regulated supply; GPIO is not a power rail.',[n])
    # Recognize only a two-resistor unloaded divider with an active upper source,
    # exactly one high-impedance input, and a real lower ground connection.
    resistors=[]
    for c in components.values():
        if CATALOG[c['part']].kind=='resistor':
            ends=[membership.get((c['id'],p)) for p in ('A','B')]
            if all(ends):resistors.append((c,ends))
    recognized=set()
    for middle,ends in nets.items():
        if middle in voltages:continue
        branches=[(c,ns[1] if ns[0]==middle else ns[0]) for c,ns in resistors if middle in ns and ns[0]!=ns[1]]
        inputs=[e for e in ends if role(e)=='input'];other=[e for e in ends if role(e) not in ('passive','input')]
        if len(branches)!=2 or len(inputs)!=1 or other:continue
        top=next(((c,n) for c,n in branches if n in voltages and n not in grounds and len(drivers[n])==1),None)
        bottom=next(((c,n) for c,n in branches if n in grounds and voltages.get(n)==[0.,0.]),None)
        if not top or not bottom or top[0]['id']==bottom[0]['id']:continue
        # Unloaded upper/lower terminals must not contain hidden extra branches/loads.
        if sum(1 for c,ns in resistors if top[1] in ns)!=1:continue
        rp=CATALOG[top[0]['part']].properties;bp=CATALOG[bottom[0]['part']].properties
        r1,r2=rp['resistance_ohm'],bp['resistance_ohm'];t1,t2=rp['tolerance_fraction'],bp['tolerance_fraction'];v=voltages[top[1]]
        low=v[0]*r2*(1-t2)/(r1*(1+t1)+r2*(1-t2));high=v[1]*r2*(1+t2)/(r1*(1-t1)+r2*(1+t2))
        voltages[middle]=[low,high];recognized|={top[0]['id'],bottom[0]['id']}
        calculations.append({'kind':'UNLOADED_RESISTOR_DIVIDER','input_net':top[1],'output_net':middle,'ground_net':bottom[1],
            'upper_resistor':top[0]['id'],'lower_resistor':bottom[0]['id'],'nominal_ratio':r2/(r1+r2),'output_high_interval_v':[low,high],
            'assumptions':['DC high level; ideal source; high impedance input; declared resistor tolerance.',
                           'No pulse edge timing, leakage, transients, power rating or acoustic fidelity certification.']})
        issue('DIVIDER_DYNAMIC_MARGIN','UNKNOWN','DC divider bounds checked; pulse timing and resistor power rating remain unverified.',[middle])
    for c,ns in resistors:
        if c['id'] not in recognized:issue('PASSIVE_NETWORK','UNKNOWN','Unsupported passive topology; no voltage inference is justified.',[c['id']])
    for n,ends in nets.items():
        inputs=[e for e in ends if role(e) in ('input','power_in')]
        outputs=drivers[n]
        if outputs and not inputs and not any(role(e)=='passive' for e in ends):issue('SIGNAL_DIRECTION','ERROR','Driven signal has no receiving input.',[n])
        for e in inputs:
            c=components[e[0]];p=pin(c['part'],e[1]);v=voltages.get(n)
            if v is None:
                issue('UNDRIVEN_INPUT','ERROR' if not any(role(k)=='passive' for k in ends) else 'UNKNOWN','Input has no supported signal source.',[list(e)])
                continue
            if p.voltage_v and (v[0]<p.voltage_v[0] or v[1]>p.voltage_v[1]):issue('VOLTAGE_INCOMPATIBLE','ERROR',f'{c["name"]}.{p.id}: {v[0]:.3f}–{v[1]:.3f} V exceeds supported {p.voltage_v} V.',[n,list(e)])
            if role(e)=='input':
                if p.high_min_v is None:issue('LOGIC_THRESHOLD','UNKNOWN',f'{c["name"]}.{p.id}: input high threshold is unavailable; compatibility is UNKNOWN.',[list(e)])
                elif v[0]<p.high_min_v:issue('LOGIC_HIGH','ERROR',f'{c["name"]}.{p.id}: minimum high {v[0]:.3f} V is below {p.high_min_v:.3f} V.',[list(e)])
    errors=sum(d['severity']=='ERROR' for d in diagnostics);unknowns=sum(d['severity']=='UNKNOWN' for d in diagnostics)
    return {'status':'INVALID' if errors else 'UNKNOWN' if unknowns else 'VALID_WITHIN_SUPPORTED_RULES',
            'supported_rules_status':'INVALID' if errors else 'VALID_WITHIN_SUPPORTED_RULES','errors':errors,'unknowns':unknowns,
            'assembly_sha256':identity(a),'netlist_sha256':digest(nets),'netlist':nets,'voltage_intervals_v':voltages,
            'diagnostics':diagnostics,'calculations':calculations,'claim':'Static supported connection checks only; no full circuit safety or real hardware verification.'}

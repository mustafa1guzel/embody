"""Additive supported electronics views. The historical catalog/rules stay intact."""
import copy,math
from .assemblies import validate,identity,netlist,fields
from .library import catalog,CATALOG,pin
from .validation import inspect
from physics.contracts import digest


def functional_interfaces():
    result={}
    for key,c in CATALOG.items():
        result[key]={'specification':{'sources':list(c.sources),'assumptions':list(c.assumptions),'confidence':c.confidence,'pins':[{'id':p.id,'physical_role':p.role,'signal_kind':'power' if p.role.startswith('power') or p.role=='ground' else 'digital' if p.role in ('input','output','configurable') else 'passive','supported_voltage_v':p.voltage_v,'gpio_capabilities':list(p.capabilities),'protocol':'UNKNOWN','current_worst_case_a':'UNKNOWN'} for p in c.pins]},'capability':{'supported':['static_connectivity','bounded_pin_roles','static_voltage_check'],'simulation':'geometric ray / position-request reference abstraction only' if c.kind in ('sensor','servo') else 'NO_ACTIVE_ELECTRONICS_SIMULATION'},'verification':{'performed':[],'status':'NOT_VERIFIED_BY_CATALOG_LISTING'},'software_interface':'reference decoded distance in m' if c.kind=='sensor' else 'reference position request in rad; no real PWM' if c.kind=='servo' else 'UNKNOWN'}
    return result


def schematic(a):
    a=validate(a);nets=netlist(a)
    return {'schema_version':1,'assembly_sha256':identity(a),'revision':a['revision'],'netlist_sha256':digest(nets),
      'symbols':[{'id':c['id'],'label':c['name'],'kind':CATALOG[c['part']].kind,'part':c['part'],'pins':[{'id':p.id,'endpoint':{'component':c['id'],'pin':p.id},'role':c['roles'].get(p.id,p.role),'reference':'GND' if p.role=='ground' else 'POWER' if p.role.startswith('power') else 'SIGNAL'} for p in CATALOG[c['part']].pins]} for c in a['components']],
      'nets':nets,'connections':copy.deepcopy(a['wires']),'truth':'Derived view only. Wire/net IDs and endpoints are exactly CIRCUITBASE, not a second graph.'}


def advanced_inspect(a,power_assumptions=None):
    a=validate(a);base=inspect(a);extra=[];calculations=[];power_assumptions=power_assumptions or []
    if not isinstance(power_assumptions,list) or len(power_assumptions)>32:raise ValueError('Bounded explicit power assumptions required')
    components={c['id']:c for c in a['components']};membership={tuple(e):n for n,ends in netlist(a).items() for e in ends}
    def issue(code,severity,message,refs):extra.append({'code':code,'severity':severity,'message':message,'references':refs})
    for c in a['components']:
        if CATALOG[c['part']].kind=='servo':
            net=membership.get((c['id'],'VCC'));ends=base['netlist'].get(net,[])
            sources=[components[e[0]] for e in ends if pin(components[e[0]]['part'],e[1]).role=='power_out']
            if not any(CATALOG[s['part']].kind=='supply' for s in sources):issue('EXTERNAL_ACTUATOR_SUPPLY','ERROR','Servo power requires an explicit external supply output; GPIO/board pass-through is not a validated power source.',[c['id'],net])
    assumptions={}
    for item in power_assumptions:
        fields(item,['component','demand_max_a','capacity_min_a','provenance'])
        if item['component'] not in components or item['component'] in assumptions:raise ValueError('Unknown/duplicate power-bound component')
        if not isinstance(item['provenance'],str) or not 1<=len(item['provenance'])<=300:raise ValueError('Explicit sourced/assumed power provenance required')
        for k in ('demand_max_a','capacity_min_a'):
            v=item[k]
            if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=20):raise ValueError('Power bounds must be null or finite 0..20 A')
        assumptions[item['component']]=item
    for n,ends in base['netlist'].items():
        loads=[e[0] for e in ends if pin(components[e[0]]['part'],e[1]).role=='power_in']
        sources=[e[0] for e in ends if pin(components[e[0]]['part'],e[1]).role=='power_out']
        if not loads:continue
        demand=[assumptions.get(c,{}).get('demand_max_a') for c in loads];caps=[assumptions.get(c,{}).get('capacity_min_a') for c in sources]
        if len(caps)!=1 or caps[0] is None or any(v is None for v in demand):issue('POWER_BUDGET','UNKNOWN','Worst-case current demand or source capacity is unavailable. No power margin inferred.',[n]);continue
        margin=caps[0]-sum(demand)
        calculations.append({'kind':'DECLARED_POWER_BOUND','net':n,'demand_max_a':sum(demand),'capacity_min_a':caps[0],'margin_a':margin,'assumptions':copy.deepcopy([assumptions[c] for c in [*loads,*sources]]),'scope':'Explicit input bounds only, not measured electrical behavior; per-source multi-rail shared capacity UNKNOWN.'})
        if margin<0:issue('POWER_BUDGET','ERROR','Declared maximum load exceeds declared minimum rail capacity.',[n])
    issue('THERMAL_MARGIN','UNKNOWN','Thermal, transient current, shared supply limits and signal integrity remain unmodeled.',[])
    diagnostics=[*base['diagnostics'],*extra];errors=sum(d['severity']=='ERROR' for d in diagnostics);unknowns=sum(d['severity']=='UNKNOWN' for d in diagnostics)
    return {**base,'status':'INVALID' if errors else 'UNKNOWN','supported_rules_status':'INVALID' if errors else 'VALID_WITHIN_SUPPORTED_RULES','errors':errors,'unknowns':unknowns,'diagnostics':diagnostics,'calculations':[*base['calculations'],*calculations],'base_rule_result':base,'power_assumptions':copy.deepcopy(power_assumptions),'rule_version':'advanced_static_v1'}

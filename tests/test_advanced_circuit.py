import copy
import pytest
from hardware.template import barrier
from hardware.assemblies import connect,remove_wire,endpoint,identity,netlist
from hardware.advanced import schematic,advanced_inspect,functional_interfaces
from hardware.validation import inspect
from engineering.interfaces import validate_interfaces
from engineering.project import new_project
from physics.contracts import digest


def test_schematic_is_derived_from_exact_graph_and_static_echo_case():
    a=barrier();bad=connect(a,endpoint('sensor','ECHO'),endpoint('board','IO19'))
    assert advanced_inspect(bad)['errors']>0 and any(d['code']=='VOLTAGE_INCOMPATIBLE' for d in advanced_inspect(bad)['diagnostics'])
    fixed=remove_wire(bad,bad['wires'][-1]['id']);v=schematic(fixed)
    assert v['connections']==fixed['wires'] and v['nets']==netlist(fixed) and v['netlist_sha256']==digest(netlist(fixed))
    assert advanced_inspect(fixed)['errors']==0 and advanced_inspect(fixed)['status']=='UNKNOWN'
    assert v['assembly_sha256']==identity(fixed) and a['revision']<bad['revision']<fixed['revision']


def test_wrong_servo_supply_and_missing_common_ground_have_real_errors():
    a=barrier();wire=next(w for w in a['wires'] if w['b']==endpoint('servo','VCC'));bad=remove_wire(a,wire['id']);bad=connect(bad,endpoint('board','IO23'),endpoint('servo','VCC'))
    assert any(d['code']=='EXTERNAL_ACTUATOR_SUPPLY' and d['severity']=='ERROR' for d in advanced_inspect(bad)['diagnostics'])
    wire=next(w for w in a['wires'] if w['b']==endpoint('servo','GND'));bad=remove_wire(a,wire['id'])
    assert any(d['code']=='REQUIRED_PIN' for d in advanced_inspect(bad)['diagnostics'])
    assert advanced_inspect(a)['errors']==0


def test_explicit_current_inequality_retains_unspecified_unknowns():
    a=barrier();claims=[{'component':'servo','demand_max_a':1.,'capacity_min_a':None,'provenance':'TEST_DECLARED_BOUND_NOT_PART_SPEC'},{'component':'supply','demand_max_a':None,'capacity_min_a':.5,'provenance':'TEST_DECLARED_BOUND_NOT_PART_SPEC'}]
    d=advanced_inspect(a,claims);assert any(x['code']=='POWER_BUDGET' and x['severity']=='ERROR' for x in d['diagnostics'])
    claims[1]['capacity_min_a']=2.;d=advanced_inspect(a,claims)
    assert not any(x['code']=='POWER_BUDGET' and x['severity']=='ERROR' for x in d['diagnostics']) and d['unknowns']>0
    assert all('UNKNOWN' in x['specification']['pins'][0]['current_worst_case_a'] for x in functional_interfaces().values())
    claims[0]['demand_max_a']=-1
    with pytest.raises(ValueError):advanced_inspect(a,claims)


def test_gpio_capability_and_dimensioned_interface_contracts():
    a=barrier();a['components'][0]['roles']['IO34']='output'
    assert any(x['code']=='GPIO_CAPABILITY' for x in advanced_inspect(a)['diagnostics'])
    p=new_project();assert validate_interfaces(p['interfaces'],p['world'],p['circuit'])==p['interfaces']
    bad=copy.deepcopy(p['interfaces']);bad[0]['unit']='rad'
    with pytest.raises(ValueError):validate_interfaces(bad,p['world'],p['circuit'])
    bad=copy.deepcopy(p['interfaces']);bad[0]['kind']='analog_sample'
    with pytest.raises(ValueError):validate_interfaces(bad,p['world'],p['circuit'])


def test_actuator_interface_requires_actual_dimensioned_actuator_and_command_pin():
    from world.objects import primitive
    p=new_project();motor=primitive('motor','drive');p['world']['objects'].append(motor)
    binding={'id':'drive_limit','kind':'actuator_limit','component':'servo','pin':'SIGNAL','world_object':'drive','unit':'N*m','sample_interval_s':.02,'abstraction':'SIMULATED_DECODED_SIGNAL'}
    assert validate_interfaces([binding],p['world'],p['circuit'])==[binding]
    for change in ({'world_object':'floor'},{'unit':'N'},{'abstraction':'MECHANICAL_REFERENCE'},{'pin':'GND'},{'pin':'VCC'}):
        with pytest.raises(ValueError):validate_interfaces([{**binding,**change}],p['world'],p['circuit'])
    motor['joint']['kind']='prismatic';motor['actuator']['unit']='N'
    assert validate_interfaces([{**binding,'unit':'N'}],p['world'],p['circuit'])
    with pytest.raises(ValueError):validate_interfaces([binding],p['world'],p['circuit'])

"""Semantic graph/electrical/security tests; no mocked electrical conclusions."""
import copy
import json
import math
import pytest
from hardware.template import barrier
from hardware.assemblies import validate,identity,endpoint,connect,remove_wire,endpoint_position,netlist
from hardware.library import catalog,catalog_hash,CATALOG
from hardware.validation import inspect
from hardware.serialization import Store,export,load
from hardware.proposals import propose,apply
from ide_api.hardware import HardwareService


def test_sourced_library_unknowns_and_board_identity():
    c=catalog();assert catalog_hash()==catalog_hash()
    assert 'WROOM-32' in c['esp32_devkitc_v4_wroom32']['model']
    assert CATALOG['towerpro_sg90_digital'].properties['stall_current_a'] is None
    assert CATALOG['towerpro_sg90_digital'].properties['signal_high_min_v'] is None
    assert all(len({p.id for p in c.pins})==len(c.pins) for c in CATALOG.values())
    assert c['regulated_dual_supply']['confidence']=='ILLUSTRATIVE_ASSUMPTION'


def test_real_divider_has_tolerance_bounds_and_unknown_current():
    a=barrier();d=inspect(a);assert d['supported_rules_status']=='VALID_WITHIN_SUPPORTED_RULES'
    assert d['status']=='UNKNOWN' and d['errors']==0
    div=d['calculations'][0];assert div['nominal_ratio']==.6
    assert div['output_high_interval_v']==pytest.approx([2.734848484848485,3.274752475247525])
    assert div['ground_net']!=div['output_net']!=div['input_net']
    assert {'CURRENT_MARGIN','LOGIC_THRESHOLD','DIVIDER_DYNAMIC_MARGIN'}<={x['code'] for x in d['diagnostics']}


def test_direct_echo_connection_is_invalid_and_real_disconnect_repairs_it():
    a=barrier();broken=connect(a,endpoint('sensor','ECHO'),endpoint('board','IO19'))
    assert any(x['code']=='VOLTAGE_INCOMPATIBLE' for x in inspect(broken)['diagnostics'])
    repaired=remove_wire(broken,broken['wires'][-1]['id'])
    assert inspect(repaired)['errors']==0
    assert sorted(netlist(repaired).values())==sorted(netlist(a).values())


def test_decorative_resistors_do_not_fix_direct_echo():
    a=barrier()
    for w in list(a['wires']):
        if 'upper' in (w['a']['component'],w['b']['component']) or 'lower' in (w['a']['component'],w['b']['component']):a=remove_wire(a,w['id'])
    a=connect(a,endpoint('sensor','ECHO'),endpoint('board','IO19'))
    d=inspect(a);assert not d['calculations'] and d['errors']>0


@pytest.mark.parametrize('ends,code',[
    (('supply','5V','supply','GND'),'SUPPLY_GROUND_CONFLICT'),
    (('board','IO18','board','IO23'),'OUTPUT_CONFLICT'),
    (('supply','5V','supply','4V8'),'OUTPUT_CONFLICT'),
])
def test_connection_faults(ends,code):
    ca,pa,cb,pb=ends;a=connect(barrier(),endpoint(ca,pa),endpoint(cb,pb))
    assert inspect(a)['status']=='INVALID' and code in {d['code'] for d in inspect(a)['diagnostics']}


def test_gpio_cannot_supply_servo_and_missing_common_ground():
    a=remove_wire(barrier(),'wire_2');a=connect(a,endpoint('board','IO23'),endpoint('servo','VCC'))
    assert 'MISSING_POWER' in {d['code'] for d in inspect(a)['diagnostics']}
    a=remove_wire(barrier(),'wire_5');assert 'REQUIRED_PIN' in {d['code'] for d in inspect(a)['diagnostics']}


def test_input_only_pin_capability_and_unconfigured_roles():
    a=barrier();a['components'][0]['roles']['IO34']='pwm'
    assert 'GPIO_CAPABILITY' in {d['code'] for d in inspect(a)['diagnostics']}
    a=barrier();a['components'][0]['roles'].pop('IO19')
    assert 'GPIO_ROLE' in {d['code'] for d in inspect(a)['diagnostics']}


@pytest.mark.parametrize('mutation',[
    lambda a:a.update(schema_version=2),lambda a:a.update(extra='not allowed'),
    lambda a:a.update(catalog_sha256='0'*64),lambda a:a.update(id='../outside'),
    lambda a:a['components'].append(copy.deepcopy(a['components'][0])),
    lambda a:a['components'][0].update(parent='absent'),
    lambda a:a['components'][0].update(position_m=[math.nan,0,0]),
    lambda a:a['components'][0].update(rotation_rad=[0,math.inf,0]),
    lambda a:a['components'][0].update(part='generic_esp32'),
    lambda a:a['wires'][0]['a'].update(pin='NONEXISTENT'),
    lambda a:a['wires'][0].update(net='absent'),
    lambda a:a['nets'].append({'id':'unused','name':'unconnected pretend net'}),
])
def test_untrusted_graph_schema_rejects_invalid_data(mutation):
    a=barrier();mutation(a)
    with pytest.raises((ValueError,TypeError)):validate(a)


def test_net_identity_cannot_hide_disconnected_edges():
    a=barrier();a['wires'][2]['net']='net_3';a['nets']=[n for n in a['nets'] if n['id']!='net_1']
    with pytest.raises(ValueError,match='explicit connected'):validate(a)


def test_transform_moves_wire_endpoint_but_never_electrical_graph():
    a=barrier();e=endpoint('board','IO18');before=endpoint_position(a,e);old=netlist(a)
    a['components'][0]['position_m'][0]+=.03
    assert endpoint_position(a,e)[0]==pytest.approx(before[0]+.03)
    a['components'][0]['rotation_rad']=[0,0,math.pi/2]
    local=CATALOG[a['components'][0]['part']].pins[2].position_m
    assert endpoint_position(a,e)[:2]==pytest.approx([a['components'][0]['position_m'][0]-local[1],a['components'][0]['position_m'][1]+local[0]])
    assert netlist(a)==old


def test_append_only_save_load_import_and_transform_identity(tmp_path):
    service=HardwareService(tmp_path);a=barrier()
    a=service.edit(a,{'kind':'transform','component':'sensor','position_m':[.1,.2,.3],'rotation_rad':[.2,.4,.7]})
    saved=service.save(a);assert service.load(saved['key'])==a
    assert service.save(a)['key']==saved['key']
    raw=json.dumps(export(a)).encode();assert load(raw)==a
    envelope=export(a);envelope['assembly']['components'][0]['name']='changed'
    with pytest.raises(ValueError,match='hash mismatch'):load(json.dumps(envelope).encode())
    assert service.load(saved['key'])==a


@pytest.mark.parametrize('raw',[b'{"schema_version":1,"schema_version":1}',b'{"x":NaN}',b'x'*120001])
def test_import_is_bounded_strict_json(raw):
    with pytest.raises(ValueError):load(raw)


def test_store_rejects_paths_and_symlinks(tmp_path):
    store=Store(tmp_path/'data');key=identity(barrier())
    for path in ('../secret','/etc/passwd','x'*64):
        with pytest.raises(ValueError):store.get(path)
    (tmp_path/'data'/(key+'.json')).symlink_to(tmp_path/'secret')
    with pytest.raises(OSError):store.get(key)
    with pytest.raises(OSError):store.save(barrier())
    (tmp_path/'link').symlink_to(tmp_path/'data',target_is_directory=True)
    with pytest.raises(ValueError):Store(tmp_path/'link'/'nested')


def test_service_add_delete_and_net_split(tmp_path):
    s=HardwareService(tmp_path);a=barrier();a=s.edit(a,{'kind':'add','part':'connector_2'});c=a['components'][-1]
    a=s.edit(a,{'kind':'rename','component':c['id'],'name':'Sensor connector'})
    a=s.edit(a,{'kind':'connect','a':endpoint(c['id'],'1'),'b':endpoint('sensor','TRIG')})
    a=s.edit(a,{'kind':'delete','component':c['id']})
    assert len(a['components'])==6 and len(a['wires'])==12
    assert inspect(a)['errors']==0


def test_proposals_require_review_and_stale_mutation_is_rejected():
    a=barrier();p=propose(a,identity(a),[{'kind':'connect','a':endpoint('sensor','ECHO'),'b':endpoint('board','IO19')}],'Deliberate defect for review')
    assert inspect(a)['errors']==0 and p['diagnostics']['errors']>0
    with pytest.raises(ValueError,match='confirmation'):apply(a,p,'')
    changed=apply(a,p,'APPLY WIRING CHANGE');assert inspect(changed)['errors']>0
    with pytest.raises(ValueError,match='Stale'):apply(changed,p,'APPLY WIRING CHANGE')
    p['assembly']['components'][0]['name']='Unreviewed mutation';p['proposed_sha256']=identity(p['assembly'])
    with pytest.raises(ValueError,match='non-wiring'):apply(a,p,'APPLY WIRING CHANGE')


@pytest.mark.parametrize('op',[{'kind':'exec','source':'print(1)'},{'kind':'write','path':'robot/controller.py'},{'kind':'connect','a':endpoint('sensor','ECHO'),'b':endpoint('board','IO19'),'source':'untrusted'}])
def test_hardware_proposals_cannot_execute_or_write_source(op):
    with pytest.raises(ValueError):propose(barrier(),identity(barrier()),[op],'Untrusted operation')

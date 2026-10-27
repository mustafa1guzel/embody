"""Small sourced catalog. Unestablished properties are explicitly unknown.

Pin coordinates and all geometry except stated servo dimensions are illustrative.
No claim of a validated footprint, PCB or complete board pin coverage.
"""
from dataclasses import dataclass, asdict
from physics.contracts import digest

SOURCES = {
    'board': 'https://docs.espressif.com/projects/esp-idf/en/v5.3.1/esp32/hw-reference/esp32/get-started-devkitc.html',
    'chip': 'https://documentation.espressif.com/esp32_datasheet_en.html',
    'sensor': 'https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf',
    'servo': 'https://towerpro.com.tw/product/sg90-7/',
}


@dataclass(frozen=True)
class Pin:
    id: str
    role: str
    position_m: tuple
    required: bool = True
    voltage_v: tuple | None = None
    high_min_v: float | None = None
    capabilities: tuple = ()
    aliases: tuple = ()


@dataclass(frozen=True)
class Component:
    id: str
    manufacturer: str
    model: str
    kind: str
    pins: tuple
    size_m: tuple
    sources: tuple
    assumptions: tuple
    properties: dict
    confidence: str
    representation: str = 'simplified_box_and_pin_markers'
    mounting: str = 'illustrative enclosure; footprint and mounting holes UNKNOWN'


CATALOG = {
 'esp32_devkitc_v4_wroom32': Component(
    'esp32_devkitc_v4_wroom32', 'Espressif', 'ESP32-DevKitC V4 / ESP32-WROOM-32', 'board', (
      Pin('5V','power_in',(-.02,-.012,0),voltage_v=(4.75,5.25)),
      Pin('GND','ground',(-.01,-.012,0)),
      Pin('IO18','configurable',(0,-.012,0),voltage_v=(-.3,3.6),high_min_v=2.475,capabilities=('input','output','pwm'),aliases=('GPIO18','J3.9')),
      Pin('IO19','configurable',(.01,-.012,0),voltage_v=(-.3,3.6),high_min_v=2.475,capabilities=('input','output','pwm'),aliases=('GPIO19','J3.8')),
      Pin('IO23','configurable',(.02,-.012,0),voltage_v=(-.3,3.6),high_min_v=2.475,capabilities=('input','output','pwm'),aliases=('GPIO23','J3.2')),
      Pin('IO34','configurable',(.02,.012,0),False,(-.3,3.6),2.475,('input',),('GPIO34','J2.5')),
    ),(.055,.028,.012),(SOURCES['board'],SOURCES['chip']),
    ('Supported header subset only; no interchangeable generic ESP32 pinout.',
     '5V input envelope 4.75–5.25 V and unloaded output high 3.3 V are illustrative assumptions.',
     'Single external power option; USB absent. VIH = 0.75 × assumed 3.3 V; input maximum = VDD + 0.3 V.'),
    {'supply_current_a':None,'output_high_v':[3.3,3.3],'dimensions_status':'ILLUSTRATIVE','pin_status':'MANUFACTURER_DOCUMENTED_SUBSET'},
    'MIXED_MANUFACTURER_AND_ASSUMPTION'),
 'hcsr04_sen15569': Component('hcsr04_sen15569','ElecFreaks / SparkFun supplier reference','HC-SR04 / SEN-15569 supported reference','sensor',(
    Pin('VCC','power_in',(-.015,-.01,0),voltage_v=(4.75,5.25)),Pin('TRIG','input',(-.005,-.01,0)),
    Pin('ECHO','output',(.005,-.01,0),voltage_v=(4.75,5.25)),Pin('GND','ground',(.015,-.01,0))),
    (.045,.02,.016),(SOURCES['sensor'],'https://github.com/sparkfun/HC-SR04_UltrasonicSensor'),
    ('Sheet specifies nominal 5 V, TTL trigger, range 0.02–4 m; module tolerance and logic bounds unavailable.',
     'Echo high 4.75–5.25 V, supply tolerance ±5% are explicit conservative illustrative assumptions; validate the physical variant.',
     'Trigger VIH/VOH margin UNKNOWN; simplified ray sensor is not acoustic simulation.'),
    {'supply_current_a':.015,'current_status':'SUPPLIER_NOMINAL_NOT_WORST_CASE','range_m':[.02,4.],'trigger_high_min_v':None,'dimensions_status':'ILLUSTRATIVE'},
    'SUPPLIER_REFERENCE_WITH_ASSUMED_LOGIC_ENVELOPE'),
 'towerpro_sg90_digital': Component('towerpro_sg90_digital','TowerPro','SG90 Digital at 4.8 V','servo',(
    Pin('VCC','power_in',(-.005,-.007,0),voltage_v=(4.8,4.8)),Pin('SIGNAL','input',(0,-.007,0)),Pin('GND','ground',(.005,-.007,0))),
    (.023,.0122,.029),(SOURCES['servo'],),
    ('Only published nominal 4.8 V is supported; voltage tolerance, stall current and 3.3 V signal compatibility UNKNOWN.',
     'Published stall torque is not a continuous usable torque rating; the simulated torque envelope is declared separately.'),
    {'supply_current_a':None,'stall_current_a':None,'signal_high_min_v':None,'stall_torque_nm':1.8*.0980665,'torque_status':'MANUFACTURER_STALL_ONLY','dimensions_status':'MANUFACTURER'},
    'MANUFACTURER_NOMINAL_WITH_UNKNOWNS'),
 'regulated_dual_supply': Component('regulated_dual_supply','Illustrative engineering source','Ideal regulated 5 V / 4.8 V dual rail','supply',(
    Pin('5V','power_out',(-.01,-.01,0),voltage_v=(4.75,5.25)),Pin('4V8','power_out',(0,-.01,0),voltage_v=(4.8,4.8)),Pin('GND','ground',(.01,-.01,0))),
    (.04,.025,.02),(),('Illustrative ideal common-ground dual supply; no physical product selected.',),
    {'current_capacity_a':None,'dimensions_status':'ILLUSTRATIVE'},'ILLUSTRATIVE_ASSUMPTION'),
}
for name, resistance in [('resistor_2200',2200.),('resistor_3300',3300.)]:
    CATALOG[name] = Component(name,'Unselected','Illustrative resistor '+str(int(resistance))+' ohm','resistor',
      (Pin('A','passive',(-.008,0,0)),Pin('B','passive',(.008,0,0))),(.012,.004,.004),(),
      ('Resistance and ±5% tolerance are declared assumptions, not a purchased part rating.',),
      {'resistance_ohm':resistance,'tolerance_fraction':.05,'power_rating_w':None,'dimensions_status':'ILLUSTRATIVE'},'ILLUSTRATIVE_ASSUMPTION')
CATALOG['connector_2'] = Component('connector_2','Unselected','Two-terminal connector','connector',
    (Pin('1','passive',(-.005,0,0),False),Pin('2','passive',(.005,0,0),False)),(.015,.009,.008),(),
    ('Independent terminals; no internal short. Current/contact rating UNKNOWN.',),{'current_capacity_a':None},'ILLUSTRATIVE_ASSUMPTION')


def catalog():
    return {key:asdict(value) for key,value in CATALOG.items()}


def catalog_hash():
    return digest(catalog())


def pin(part, identifier):
    return next((p for p in CATALOG[part].pins if p.id==identifier), None)

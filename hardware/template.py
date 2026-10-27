"""Human-defined reference assembly; no autonomous AI generation claim."""
from .assemblies import empty, instance, connect, endpoint, validate


def barrier():
    a=empty();a['id']='sensor_barrier'
    for key,part,pos in [('board','esp32_devkitc_v4_wroom32',[-.07,0,.015]),('sensor','hcsr04_sen15569',[.03,.04,.015]),
                         ('servo','towerpro_sg90_digital',[.05,-.03,.015]),('supply','regulated_dual_supply',[-.07,-.07,.015]),
                         ('upper','resistor_2200',[-.005,.015,.015]),('lower','resistor_3300',[-.005,-.015,.015])]:
        a['components'].append(instance(a,part,key,key,pos))
    a['components'][0]['roles']={'IO18':'output','IO19':'input','IO23':'pwm'}
    edges=[('supply','5V','board','5V'),('supply','5V','sensor','VCC'),('supply','4V8','servo','VCC'),
           ('supply','GND','board','GND'),('supply','GND','sensor','GND'),('supply','GND','servo','GND'),
           ('board','IO18','sensor','TRIG'),('sensor','ECHO','upper','A'),('upper','B','board','IO19'),
           ('upper','B','lower','A'),('lower','B','supply','GND'),('board','IO23','servo','SIGNAL')]
    for ca,pa,cb,pb in edges:a=connect(a,endpoint(ca,pa),endpoint(cb,pb))
    # Deterministic template IDs permit reproducible evidence and stable round trips.
    mapping={n['id']:'net_'+str(i) for i,n in enumerate(a['nets'])}
    for i,n in enumerate(a['nets']):n.update(id=mapping[n['id']],name='reference_'+str(i))
    for i,w in enumerate(a['wires']):w.update(id='wire_'+str(i),net=mapping[w['net']])
    return validate(a)

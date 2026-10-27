"""SI envelopes, initial conditions and uncertainty classes are explicit."""
from dataclasses import dataclass,asdict
from physics.contracts import finite


@dataclass(frozen=True)
class Parameter:
    unit:str
    low:float
    high:float
    nominal:float
    near_low:float
    near_high:float
    kind:str='physical_parameter'

    def validate(self,value):
        finite('parameter',value)
        if not self.low<=value<=self.high:raise ValueError('Parameter outside the frozen operating envelope')


PARAMETERS={
 'rail':{
  'mass_kg':Parameter('kg',1.,4.,2.,1.8,2.2),
  'force_n':Parameter('N',2.,6.,4.,3.6,4.4),
  'speed_mps':Parameter('m/s',.4,1.2,1.2,1.08,1.2,'initial_condition'),
  'gap_m':Parameter('m',.35,2.2,1.77,1.593,1.947,'initial_condition'),
  'initial_position_m':Parameter('m',-.15,.15,0.,-.015,.015,'initial_condition')},
 'arm':{
  'link1_mass_kg':Parameter('kg',.5,2.5,1.,.9,1.1),
  'link2_mass_kg':Parameter('kg',.3,1.5,.6,.54,.66),
  'shoulder_torque_nm':Parameter('N*m',1.,4.5,3.,2.7,3.3),
  'elbow_torque_nm':Parameter('N*m',.4,2.2,1.5,1.35,1.65),
  'damping_nm_s_per_rad':Parameter('N*m*s/rad',.01,.25,.05,.045,.055),
  'q0_shoulder_rad':Parameter('rad',-2.55,2.55,0.,-.1,.1,'initial_condition'),
  'q0_elbow_rad':Parameter('rad',-2.35,2.35,.3,.2,.4,'initial_condition'),
  'goal_shoulder_rad':Parameter('rad',-1.8,1.8,.7,.65,.75,'task_definition'),
  'goal_elbow_rad':Parameter('rad',-1.8,1.8,-1.,-1.05,-.95,'task_definition')}
}


def nominal(family):return {k:p.nominal for k,p in PARAMETERS[family].items()}
def schema():return {f:{k:asdict(p) for k,p in params.items()} for f,params in PARAMETERS.items()}
def validate(family,values):
    if family not in PARAMETERS or set(values)!=set(PARAMETERS[family]):raise ValueError('Unknown family or parameter fields')
    for k,p in PARAMETERS[family].items():p.validate(values[k])
    return dict(values)


def simplicity(family,values):
    validate(family,values)
    distances=[abs(values[k]-p.nominal)/(p.high-p.low) for k,p in PARAMETERS[family].items()]
    return (sum(v>1e-12 for v in distances),sum(distances))

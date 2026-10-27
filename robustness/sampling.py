"""Fixed counts; independent random strata and deliberate boundary points differ."""
import random
from physics.contracts import digest
from .parameters import PARAMETERS,nominal,validate

SEEDS={'rail':104729,'arm':130363}


def scenario(family,parameters,stratum,index,seed):
    values=validate(family,parameters)
    data={'family':family,'parameters':values,'stratum':stratum,'index':index,'seed':seed}
    return {'id':family+'_'+digest(data)[:20],**data}


def boundaries(family):
    n=nominal(family)
    changes=([{'mass_kg':4.},{'force_n':2.},{'speed_mps':.4},{'gap_m':.35},{'gap_m':2.2},
              {'mass_kg':4.,'force_n':2.,'gap_m':.35},{'mass_kg':1.,'force_n':6.,'gap_m':.35},
              {'mass_kg':4.,'force_n':2.,'speed_mps':.4,'gap_m':2.2,'initial_position_m':.15}] if family=='rail' else
             [{'link1_mass_kg':2.5,'link2_mass_kg':1.5},{'shoulder_torque_nm':1.,'elbow_torque_nm':.4},
              {'link1_mass_kg':2.5,'link2_mass_kg':1.5,'shoulder_torque_nm':1.,'elbow_torque_nm':.4},
              {'link1_mass_kg':.5,'link2_mass_kg':.3,'shoulder_torque_nm':4.5,'elbow_torque_nm':2.2},
              {'damping_nm_s_per_rad':.01},{'q0_shoulder_rad':2.55,'q0_elbow_rad':-2.35},
              {'q0_shoulder_rad':-2.55,'q0_elbow_rad':2.35},{'goal_shoulder_rad':-1.8,'goal_elbow_rad':1.8}])
    return [{**n,**v} for v in changes]


def sample(family,seed=None):
    seed=SEEDS[family] if seed is None else seed
    if type(seed) is not int or not 0<=seed<2**32:raise ValueError('A bounded integer seed is required')
    result=[scenario(family,nominal(family),'anchor',0,seed)]
    for stratum,count,offset in [('nominal_uniform',15,1),('wide_uniform',16,2)]:
        rng=random.Random(seed+offset)
        for i in range(count):
            p={k:(v.near_low+(v.near_high-v.near_low)*rng.random() if stratum=='nominal_uniform'
                  else v.low+(v.high-v.low)*rng.random()) for k,v in PARAMETERS[family].items()}
            result.append(scenario(family,p,stratum,i,seed+offset))
    result.extend(scenario(family,p,'boundary',i,seed) for i,p in enumerate(boundaries(family)))
    return result

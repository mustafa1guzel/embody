"""Two-link planar kinematics only. No dynamic or arbitrary-program certificate."""
import math
from .contracts import finite


def inputs(lengths, q):
    if len(lengths) != 2 or len(q) != 2: raise ValueError('Planar evaluator requires two links/joints')
    for l in lengths: finite('length', l, positive=True)
    for v in q: finite('angle', v)


def forward(lengths, q):
    inputs(lengths, q); l1, l2 = lengths; a, b = q
    return (l1*math.cos(a)+l2*math.cos(a+b), l1*math.sin(a)+l2*math.sin(a+b))


def jacobian(lengths, q):
    inputs(lengths, q); l1, l2 = lengths; a, b = q
    return ((-l1*math.sin(a)-l2*math.sin(a+b), -l2*math.sin(a+b)),
            (l1*math.cos(a)+l2*math.cos(a+b), l2*math.cos(a+b)))


def inverse(lengths, target, limits, tolerance=1e-10):
    inputs(lengths, (0, 0))
    if len(target) != 2 or len(limits) != 2: raise ValueError('Invalid planar target/limits')
    for value in target: finite('target', value)
    finite('tolerance', tolerance, nonnegative=True)
    for pair in limits:
        if len(pair) != 2: raise ValueError('Invalid joint limits')
        for v in pair: finite('joint limit', v)
        if pair[0] > pair[1] or pair[1]-pair[0] > 4*math.pi: raise ValueError('Unsupported limit interval')
    l1, l2 = lengths; x, y = target; radius = math.hypot(x, y)
    if radius < abs(l1-l2)-tolerance or radius > l1+l2+tolerance: return []
    if radius <= tolerance: return []  # Equal-length folded continuum is unsupported.
    cosine = (radius*radius-l1*l1-l2*l2)/(2*l1*l2)
    if not -1-tolerance <= cosine <= 1+tolerance: return []
    angle = math.acos(max(-1, min(1, cosine))); solutions = []
    for q2 in (angle, -angle):
        q1 = math.atan2(y, x)-math.atan2(l2*math.sin(q2), l1+l2*math.cos(q2))
        choices = []
        for q, (low, high) in zip((q1, q2), limits):
            choices.append([q+2*math.pi*k for k in range(math.ceil((low-q-tolerance)/(2*math.pi)),
                                                         math.floor((high-q+tolerance)/(2*math.pi))+1)])
        for a in choices[0]:
            for b in choices[1]:
                if math.dist(forward(lengths, (a, b)), target) <= max(tolerance, 1e-12):
                    if not any(math.dist((a,b), s) <= 1e-10 for s in solutions): solutions.append((a,b))
    return solutions


def assess(contract, lengths, *, premises=True, plane_height_m=.25):
    result = {'status':'UNKNOWN', 'kinematic_feasibility':'UNKNOWN', 'dynamic_feasibility':'UNKNOWN',
              'contract_sha256':contract.identity, 'model_sha256':contract.model_sha256,
              'controller_safety':'UNKNOWN', 'witnesses_rad':[], 'singular_witnesses':[],
              'equations':{'forward':'x=L1 cos(q1)+L2 cos(q1+q2); y=L1 sin(q1)+L2 sin(q1+q2)',
                           'jacobian':'J=[[-L1 sin(q1)-L2 sin(q1+q2),-L2 sin(q1+q2)],[L1 cos(q1)+L2 cos(q1+q2),L2 cos(q1+q2)]]',
                           'determinant':'det(J)=L1*L2*sin(q2)', 'radial':'abs(L1-L2)<=r<=L1+L2 (unrestricted chain only)'},
              'limitations':['IK does not prove torque, timing, collision or controller feasibility.',
                             'No verification or installation approval is granted.'], 'explanation':''}
    if (not premises or contract.family!='arm' or len(contract.joints) != 2
            or contract.joint_axes_world!=((0,0,1),(0,0,1)) or any(j.kind != 'revolute' for j in contract.joints)):
        result['explanation']='Unsupported analytical premises.'; return result
    x,y,z = contract.target_m; l1,l2=lengths; radius=math.hypot(x,y)
    result['radial_bounds_m']=[abs(l1-l2),l1+l2];result['radius_m']=radius
    result['target_tolerance_m']=contract.target_tolerance_m
    radial_distance=max(0,abs(l1-l2)-radius,radius-l1-l2)
    distance=math.hypot(radial_distance,z-plane_height_m)
    result['distance_to_unrestricted_workspace_m']=distance
    if distance > contract.target_tolerance_m+1e-10:
        result.update(status='PROVEN_INFEASIBLE',kinematic_feasibility='INFEASIBLE',
                      explanation='Even the unrestricted fixed-plane radial workspace misses the entire target tolerance ball. Controller changes cannot alter link reach.')
        return result
    solutions=inverse(lengths,(x,y),[j.position_range for j in contract.joints])
    result['witnesses_rad']=[list(s) for s in solutions]
    result['singular_witnesses']=[abs(l1*l2*math.sin(s[1]))<1e-10 for s in solutions]
    if solutions:
        result.update(status='CONDITIONALLY_FEASIBLE',kinematic_feasibility='FEASIBLE',
                      explanation='A target-center IK witness satisfies joint limits; dynamics and collisions remain unverified.')
    else:
        result['explanation']='No supported joint-limit witness for the center. The nonzero tolerance ball/obstacles are not certified by this evaluator.'
    return result

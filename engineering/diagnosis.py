"""Evidence-led categories; no requirement relaxation or automatic code fix."""
from devices.contracts import DeviceSpec
from devices.simulation import analytical
from hardware.advanced import advanced_inspect

CATEGORIES=['ELECTRICAL_INCOMPATIBILITY','MISSING_INTERFACE_POWER_PRECONDITION','CONTROLLER_BEHAVIOR','ACTUATOR_CAPABILITY','MASS_GEOMETRY','FORBIDDEN_CONTACT','TASK_REQUIREMENT','PHYSICALLY_INFEASIBLE_GOAL','UNSUPPORTED_MODEL','MISSING_INFORMATION']


def diagnose(project,measurement=None):
    electrical=advanced_inspect(project['circuit']);findings=[]
    def add(category,confidence,evidence,recommendation):findings.append({'category':category,'confidence':confidence,'evidence':evidence,'recommendation':recommendation})
    if project.get('creation',{}).get('family')=='sensor_barrier' and project['creation']['state']=='BUILT':
        from .barrier_repair import preflight_project
        try:
            pf=preflight_project(project)
            if any(f['code']=='INSUFFICIENT_STATIC_TORQUE' for f in pf['findings']):
                add('ACTUATOR_CAPABILITY','CONSERVATIVE_STATIC_SCREEN',pf,'Review beam load and supported authority; the 1.2 static screen is not a replacement for dynamic acceptance.')
            if pf['native']['initial_contacts'] or measurement and measurement.get('generated_world_binding') and not measurement['acceptance']['checks']['no_contacts']:
                add('FORBIDDEN_CONTACT','NATIVE_CONTACT_EVIDENCE',{'initial_native':pf['native'],'measured_contact_samples':sum(s['contacts']>0 for s in measurement['samples']) if measurement and measurement.get('generated_world_binding') else None},'Review physical support/beam/pivot clearance. Preserve collision masks and the original no_contacts requirement.')
        except ValueError as exc:add('UNSUPPORTED_MODEL','OBSERVED',{'error':str(exc)},'Resolve unsupported generated geometry before physical preflight.')
    if electrical['errors']:add('ELECTRICAL_INCOMPATIBILITY','STATIC_SUPPORTED_RULES',[d for d in electrical['diagnostics'] if d['severity']=='ERROR'],'Repair electrical preconditions before dynamics.')
    if not measurement:add('MISSING_INFORMATION','OBSERVED',[],'Run a supported trusted simulation; do not infer dynamics from component labels.')
    elif measurement.get('execution')!='COMPLETED':add('UNSUPPORTED_MODEL','OBSERVED',[measurement.get('blocked_reason','No supported executed dynamics')],'Resolve model/interface preconditions before physical claims.')
    else:
        if measurement.get('generated_world_binding'):
            from .generated_contract import GeneratedSpec
            spec=GeneratedSpec.from_dict(measurement['device_spec'])
        else:spec=DeviceSpec.from_dict(measurement['device_spec'])
        guard=analytical(spec);accept=measurement['acceptance'];ratio=guard['initial_gravity_torque_nm']/spec.mechanical.torque_limit_nm
        if not accept['checks']['opening_deadline'] and ratio>1:
            add('ACTUATOR_CAPABILITY','MEASURED_SUPPORTED_REFERENCE',{'acceptance':accept,'analytical':guard,'gravity_to_actuator_ratio':ratio,'model_sha256':measurement['compiled']['model_sha256'],'contract_sha256':measurement['contract_sha256']},'Reduce beam mass in the declared envelope or select a separately justified stronger actuator. Keep the fixed deadline; a code patch is not established as sufficient.')
            add('MASS_GEOMETRY','DECLARED_AND_NATIVE_COMPILED',measurement['compiled'],'Review supported beam load/inertia; test any correction with fresh MuJoCo evidence.')
        if not accept['checks']['no_closing_on_near_object']:add('CONTROLLER_BEHAVIOR','MEASURED',accept,'Review close_while_near behavior through the existing controller/configuration review boundary.')
        if all(accept['checks'].values()):add('TASK_REQUIREMENT','MEASURED_SUPPORTED_REFERENCE',accept,'All fixed reference checks passed in this run; no universal safety claim.')
    return {'origin':'DETERMINISTIC_EVIDENCE_RULES; not model reasoning','categories':CATEGORIES,'findings':findings,'software_only_fix':'NOT_ESTABLISHED' if any(f['category']=='ACTUATOR_CAPABILITY' for f in findings) else 'REQUIRES_CASE_EVIDENCE','physical_infeasibility':'NOT_PROVEN; compliant stops prevent the simple bound from being a general impossibility proof','unknowns':['Electrical current/thermal behavior','Real actuator dynamics','Hardware fidelity'],'requirements_changed':False}

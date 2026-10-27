"""Explicit OFFLINE test oracle only. Never imported by transmitted context."""
import copy,json
from pathlib import Path
from .assembly_plan import GOAL
ROOT=Path(__file__).resolve().parents[1]

def fixture_plan():
 data=json.loads((ROOT/'artifacts/phase18d/20261025/examples/rover/setup.json').read_text())
 return {'schema_version':1,'goal':GOAL,'roles':{'root_body_id':'rover_root','chassis_part_id':'shape_chassis','front_axle_part_id':'shape_front_axle','rear_axle_part_id':'shape_rear_axle','wheels':{k:{'part_id':'shape_'+k+'_wheel','joint_body_id':k+'_wheel_joint'} for k in ('front_left','front_right','rear_left','rear_right')},'motor_mount_parts':{'left':'shape_rear_left_motor_mount','right':'shape_rear_right_motor_mount'}},
 'assumptions':['OFFLINE_PROTOCOL_FIXTURE: explicit developer mass and constant motor assumptions from immutable Phase18D oracle; not model reasoning.'],
 'limitations':['No steering, suspension, continuous wheel rotation, wiring/MCU execution, robust locomotion or hardware safety.'],
 'explanation':'DETERMINISTIC OFFLINE TEST ORACLE, NOT LIVE AI. Existing typed batches are deliberately used only to exercise plan validation, reconstruction, review and native verification.',
 'steps':[{'id':'fixture_batch_'+str(i),'depends_on':['fixture_batch_'+str(i-1)] if i else [],'purpose':s['description'],'operations':copy.deepcopy(s['operations'])} for i,s in enumerate(data['setup_receipts'])]}

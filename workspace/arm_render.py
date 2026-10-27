"""Native MuJoCo visualization of pinned measured states, never a new rollout."""
import argparse
from pathlib import Path
import hashlib
import mujoco
import numpy as np
from PIL import Image
from core.simulation import write_json
from workspace.arm_data import default_arm_recording


def render(output,scenario='arm_nominal',steps=(0,400,800)):
    recording=default_arm_recording();experiment=recording.experiment(scenario)
    if experiment['scene'] is None:raise ValueError('No dynamic states exist for an infeasible task')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);rows=[]
    for variant,trajectory in experiment['variants'].items():
        summary=trajectory['summary'];xml=recording.read(summary['artifact_references']['effective_model.xml']).decode()
        model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
        camera=mujoco.MjvCamera();camera.lookat[:]=[0,.05,.2];camera.distance=2.7;camera.azimuth=90;camera.elevation=-65
        with mujoco.Renderer(model,height=480,width=640) as renderer:
            for step in steps:
                s=trajectory['samples'][step];data.qpos[:]=s['qpos_rad'];data.qvel[:]=s['qvel_rad_s'];data.ctrl[:]=s['command'];mujoco.mj_forward(model,data)
                renderer.update_scene(data,camera=camera);pixels=renderer.render().copy()
                if pixels.shape!=(480,640,3) or pixels.std()<5:raise RuntimeError('Empty native arm rendering')
                renderer.enable_segmentation_rendering()
                try:
                    segmentation=renderer.render();counts={name:int(np.count_nonzero((segmentation[:,:,0]==model.geom(name).id)&(segmentation[:,:,1]==int(mujoco.mjtObj.mjOBJ_GEOM)))) for name in ('link1_box','link2_box','tool_marker','target_marker')}
                    if min(counts.values())==0:raise RuntimeError('Required arm geometry is not visible: '+str(counts))
                finally:renderer.disable_segmentation_rendering()
                path=output/f'{variant}_{step:04d}.png';Image.fromarray(pixels).save(path)
                rows.append({'variant':variant,'step':step,'time_s':s['time'],'qpos_rad':s['qpos_rad'],
                    'target_error_m':s['target_error_m'],'source_sha256':summary['controller_sha256'],
                    'telemetry_sha256':recording.index['files'][recording.reference(summary['artifact_references']['telemetry.json'])],
                    'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'visible_geom_pixels':counts})
    index={'status':'PASS','method':'Native MuJoCo rendering of pinned measured states, not a new simulation.',
           'recording_sha256':recording.identity,'scenario':scenario,'frames':rows}
    write_json(output/'index.json',index);return index


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--scenario',default='arm_nominal')
    args=p.parse_args();print(render(args.output,args.scenario)['status'])

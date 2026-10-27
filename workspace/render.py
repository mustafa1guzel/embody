"""Reconstruct native frames from measured states, without executing candidate code.

This is visualization of recorded evidence, not a fresh simulation or verification.
"""
import argparse
from pathlib import Path

import mujoco

from core.simulation import _capture, collision_surfaces, write_json
from workspace.data import LABELS, SCENARIOS, default_recording


def render_recording(recording, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)  # never replace previous render evidence
    index = {'status':'INCOMPLETE','recording_inventory_sha256':recording.inventory_sha256,
             'renderer':'mujoco.Renderer / existing core.simulation._capture',
             'basis':'Recorded telemetry state reconstruction; no new dynamics or acceptance evaluation',
             'candidate_code_executed':False,'new_simulations_executed':0,'scenarios':{}}
    write_json(output/'index.json',index)
    for scenario in SCENARIOS:
        index['scenarios'][scenario] = {}
        for variant in LABELS:
            trajectory = recording.trajectory(scenario,variant)
            samples, summary = trajectory['samples'], trajectory['summary']
            steps = {0,200,400,600,min(samples,key=lambda r:r['wall_clearance'])['step']}
            for event in ('braking_onset','first_wall_contact'):
                if summary[event] is not None:
                    steps.add(summary[event]['step'])
            model = mujoco.MjModel.from_xml_string(trajectory['xml'])
            data = mujoco.MjData(model)
            directory = output/scenario/variant
            directory.mkdir(parents=True)
            frames=[]
            with mujoco.Renderer(model,height=768,width=1024) as renderer:
                for step in sorted(steps):
                    sample = samples[step]
                    if sample['step'] != step:
                        raise ValueError('Recorded step index mismatch')
                    data.qpos[0],data.qvel[0] = sample['position'],sample['velocity']
                    data.ctrl[0],data.time = sample['control'],sample['time']
                    mujoco.mj_forward(model,data)
                    if abs(collision_surfaces(model,data)['wall_clearance']-sample['wall_clearance'])>1e-12:
                        raise ValueError('Native state reconstruction differs from measured geometry')
                    frame = _capture(renderer,model,data,sample,directory)
                    frame['path'] = str(Path(scenario)/variant/frame['path'])
                    frames.append(frame)
            index['scenarios'][scenario][variant]=frames
    index['status']='COMPLETE'
    write_json(output/'index.json',index)
    return index


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    index=render_recording(default_recording(),args.output)
    print('Native recorded-state frames:',sum(len(frames) for rows in index['scenarios'].values() for frames in rows.values()))


if __name__=='__main__':
    main()

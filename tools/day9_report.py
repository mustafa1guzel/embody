"""Reproducible measured comparison, without model calls or source execution."""
import argparse
from pathlib import Path
import json
from xml.sax.saxutils import escape
from core.simulation import write_json
from workspace.arm_data import default_arm_recording


def measurements():
    r=default_arm_recording();result={'robot_family':'arm','recording_sha256':r.identity,'scenarios':{}}
    for scenario in r.metadata()['scenarios']:
        e=r.experiment(scenario);rows={}
        for variant,t in e['variants'].items():
            s=t['summary'];rows[variant]={k:s[k] for k in ('simulation_execution','physical_safety_status','independent_verification','analytical_guard')}
            if t['samples']:
                rows[variant].update(controller_sha256=s['controller_sha256'],safety_acceptance=s['safety_acceptance'],
                    profiler=s['profiler'],sample_count=len(t['samples']),independent=t['independent'])
        result['scenarios'][scenario]=rows
    return result


def plots(output):
    """SVG coordinates are computed directly from the complete measured arrays."""
    r=default_arm_recording();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for scenario in r.metadata()['scenarios']:
        e=r.experiment(scenario)
        if e['scene'] is None:continue
        variants=e['variants'];fields=[('target_error_m','Target error (m)',None),('qpos_rad','Joint angle (rad)',0),('qvel_rad_s','Joint velocity (rad/s)',0),('generalized_torque_nm','Joint torque (N m)',0)]
        parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 1000 1000">',
            '<rect width="1000" height="1000" fill="white"/>',f'<text x="60" y="30" font-size="18">{escape(scenario)} — independently measured MuJoCo</text>',
            '<text x="60" y="52" font-size="12">Baseline: red; GPT candidate: teal. Solid: shoulder/scalar error; dashed: elbow. No interpolation.</text>']
        for panel,(field,label,_) in enumerate(fields):
            top=95+panel*220;values=[v for t in variants.values() for s in t['samples'] for v in ([s[field]] if field=='target_error_m' else s[field])]
            low=min(0,min(values));high=max(values);span=high-low or 1
            parts.append(f'<text x="60" y="{top-10}" font-size="14">{label}</text><path d="M60 {top} V{top+160} H940" fill="none" stroke="#aaa"/>')
            for v,t in variants.items():
                for j in ([0] if field=='target_error_m' else [0,1]):
                    points=' '.join(f'{60+s["time"]/t["samples"][-1]["time"]*880:.3f},{top+160-((s[field] if field=="target_error_m" else s[field][j])-low)/span*160:.3f}' for s in t['samples'])
                    color='#bb3e37' if v=='original' else '#087e79';dash=' stroke-dasharray="5 3"' if j else ''
                    parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.2"{dash}/>')
            parts.extend([f'<text x="5" y="{top+10}" font-size="11">{high:.3g}</text>',f'<text x="5" y="{top+160}" font-size="11">{low:.3g}</text>',f'<text x="60" y="{top+180}" font-size="11">0 s</text>',f'<text x="910" y="{top+180}" font-size="11">4 s</text>'])
        parts.append(f'<text x="60" y="990" font-size="10">Recording SHA-256: {r.identity}</text></svg>')
        (output/(scenario+'.svg')).write_text(''.join(parts))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if (args.output/'measurements.json').exists():raise FileExistsError('Refusing to replace report evidence')
    write_json(args.output/'measurements.json',measurements());plots(args.output/'plots')

"""New-directory-only baseline reproduction. No model calls or candidate execution."""
import argparse
import hashlib
from pathlib import Path
from core.robots.arm import ArmFamily,TARGET,MODEL,CONFIG,EVALUATION
from core.simulation import ROOT,write_json


def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    frozen={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (TARGET,MODEL,CONFIG,EVALUATION)}
    write_json(output/'frozen_inputs.json',frozen)
    family=ArmFamily(evaluation=True)
    results={s:family.trusted(s,output/'baseline_final')[0] for s in family.scenarios}
    write_json(output/'baseline_final_index.json',results)
    (output/'baseline_analysis_before_gpt.md').write_text(
        'Expected: reach the fixed target and settle under the frozen criteria.\n'
        'Actual outcomes are in baseline_final_index.json and the independently rerun telemetry.\n'
        'Developer hypothesis from source: the positive velocity term reinforces motion.\n'
        'This is an AI-assisted developer definition, not live-agent reasoning.\n'
        'Criteria and source identities were frozen before candidate comparison.\n')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(prepare(args.output).keys())

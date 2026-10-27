import argparse
from pathlib import Path
from .builder import freeze
from .batch import run

parser=argparse.ArgumentParser(description='Day 10 offline freeze or explicitly approved qualified-VM evaluation; never calls OpenAI.')
sub=parser.add_subparsers(dest='operation',required=True)
a=sub.add_parser('freeze');a.add_argument('--output',type=Path,required=True)
b=sub.add_parser('evaluate');b.add_argument('--experiment',type=Path,required=True);b.add_argument('--approve-experiment',required=True);b.add_argument('--refresh-containment',action='store_true')
args=parser.parse_args()
if args.operation=='freeze':print(freeze(args.output).identity)
else:print(run(args.experiment,approved_sha=args.approve_experiment,refresh_containment=args.refresh_containment)['status'])

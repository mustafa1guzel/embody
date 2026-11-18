"""Public supported v1 local regression selection; no historical private fixtures.

Unrestricted archival tests are retained separately; their absence is not a pass.
The core public policy originates in research_release_verify.BACKEND. Trusted
native development fixtures are allowed; provider/network/VM/history writes are not.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
from tools.research_release_verify import BACKEND
ROOT=Path(__file__).resolve().parents[1]
PUBLIC_SUITES=BACKEND+[
 'tests/test_product_alpha.py','tests/test_robot_toolkit.py','tests/test_engineering_agent.py',
 'tests/test_engineering_agent_live.py','tests/test_requirement_references.py','tests/test_agent_reliability.py',
 'tests/test_agent_deadline.py','tests/test_api_budget.py','tests/test_api_credentials.py',
 'tests/test_responses_continuation.py','tests/test_circuitbase.py','tests/test_advanced_circuit.py',
 'tests/test_shapebase.py','tests/test_shapebase_api.py','tests/test_local_workbench.py']
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args();out=Path(args.output).absolute()
 if out.exists():p.error('Use a new output directory; previous test evidence is never replaced')
 out.mkdir(parents=True,mode=0o700)
 # An empty history baseline is only a test guard input, never paid accounting.
 (out/'guard_baseline.json').write_text(json.dumps({'historical_files':{}}))
 command=[sys.executable,'-B','-m','pytest','-ra','-p','no:cacheprovider','-p','tools.v100_test_guards','-m','not live_vm','--basetemp='+str(out/'temporary_projects'),*PUBLIC_SUITES]
 (out/'command.json').write_text(json.dumps({'command':command,'scope':'PUBLIC_SUPPORTED_CORE_WITH_TRUSTED_NATIVE_FIXTURES','archival_tests_not_claimed':'Private Day/Phase fixtures and live VM tests are not run by this documented selection.'},indent=2))
 with (out/'pytest.txt').open('x') as f:r=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','EMBODY_V100_BASELINE':str(out/'guard_baseline.json'),'EMBODY_V100_GUARD_OUTPUT':str(out/'guard.json')},stdout=f,stderr=subprocess.STDOUT)
 print('Public local regression exit:',r.returncode,'Evidence:',out);raise SystemExit(r.returncode)
if __name__=='__main__':main()

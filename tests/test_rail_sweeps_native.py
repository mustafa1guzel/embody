"""Explicit bounded real-native demonstration: three primary + three fresh replays."""
import json,os
from pathlib import Path
import mujoco
from ide_api import rail_sweeps as lab

def test_three_genuine_reference_cases_and_fresh_replays(tmp_path,monkeypatch):
    root=Path(os.environ.get('EMBODY_SWEEP_EVIDENCE_DIR',tmp_path/'native'))
    assert not root.exists(), 'Write-once demonstration root; never rerun into previous evidence'
    original=mujoco.mj_step;steps=[]
    def counted(model,data):steps.append(1);return original(model,data)
    monkeypatch.setattr(mujoco,'mj_step',counted)
    s=lab.RailSweeps(root);value={'experiment_id':lab.EXPERIMENT,'controller_id':lab.CONTROLLER,'source_sha256':lab.source_identity(),
       'nonce':'b'*32,'confirmation':lab.CONFIRMATION,'criteria':dict(lab.DEFAULT_CRITERIA),'cases':[
       {'mass_kg':2.,'speed_mps':.4,'force_n':4.,'gap_m':1.77},
       {'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':2.2},
       {'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49}]}
    s.start(value,lambda op:{'job_id':'explicit-native-test'});s.execute(value['nonce']);state=s.read(value['nonce'])
    (root/'demonstration.json').write_text(json.dumps({'state':state,'actual_native_rollouts':len(steps)//600,'actual_native_steps':len(steps)},indent=2)+'\n')
    assert state['status']=='COMPLETED',state
    assert len(steps)==3600, 'Hard development budget: exactly six 600-step native rollouts'
    assert len(state['cases'])==3
    for item in state['cases']:
        r=s.case(value['nonce'],item['case_id']);assert len(r['samples'])==601 and len(r['replay']['samples'])==601
        assert r['replay']['status']=='PASS';assert r['metrics']['maximum_actuator_force_n']<=item['parameters']['force_n']+1e-12
        assert r['samples'][0]['velocity']==item['parameters']['speed_mps'];assert abs(r['samples'][0]['wall_clearance']-item['parameters']['gap_m'])<=1e-12
        assert r['checks']['fresh_replay'] and r['checks']['no_unexpected_contacts'];assert r['verdict'] in ('PASS','FAIL')
    assert state['cases'][0]['verdict']=='PASS'

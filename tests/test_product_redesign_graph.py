"""Real graph/revision contracts used by visual editing; no model or VM mocks."""
import pytest
from ide_api.engineering import EngineeringService
from ide_api.hardware import HardwareService
from engineering.project import identity
from hardware.advanced import schematic,advanced_inspect
from hardware.assemblies import endpoint


def test_visual_transform_round_trip_keeps_graph_and_restores_through_new_revision(tmp_path):
    service=EngineeringService(tmp_path/'project');hardware=HardwareService(tmp_path/'hardware')
    initial=service.current();key=service.save(identity(initial),initial['revision'])['key']
    visual=hardware.edit(initial['circuit'],{'kind':'transform','component':'sensor','position_m':[.04,-.08,.02],'rotation_rad':[.2,.3,1.2]})
    changed=service.replace_circuit(identity(initial),0,visual)
    assert changed['circuit']['wires']==initial['circuit']['wires']
    assert schematic(changed['circuit'])['connections']==visual['wires']
    assert service.current()['circuit']['components']==visual['components']
    restored=service.restore(identity(changed),changed['revision'],key)
    assert restored['circuit']['components']==initial['circuit']['components']
    assert restored['revision']>changed['revision'] and restored['circuit']['revision']>visual['revision']


def test_connection_preview_does_not_commit_and_real_commit_preserves_unknowns(tmp_path):
    service=EngineeringService(tmp_path/'project');hardware=HardwareService(tmp_path/'hardware');initial=service.current()
    preview=hardware.edit(initial['circuit'],{'kind':'connect','a':endpoint('sensor','ECHO'),'b':endpoint('board','IO19')})
    assert service.current()==initial and advanced_inspect(preview)['errors']>0
    changed=service.replace_circuit(identity(initial),0,preview)
    assert changed['revision']==1 and len(changed['circuit']['wires'])==len(initial['circuit']['wires'])+1
    repaired=hardware.edit(changed['circuit'],{'kind':'disconnect','wire_id':preview['wires'][-1]['id']})
    final=service.replace_circuit(identity(changed),1,repaired)
    checks=advanced_inspect(final['circuit']);assert checks['errors']==0 and checks['unknowns']==9 and checks['status']=='UNKNOWN'
    assert schematic(final['circuit'])['connections']==final['circuit']['wires']


@pytest.mark.parametrize('bad_pin',['CC','GPIO19','3V3'])
def test_visual_aliases_or_decorative_pins_cannot_create_electrical_edges(tmp_path,bad_pin):
    service=EngineeringService(tmp_path/'project');hardware=HardwareService(tmp_path/'hardware');initial=service.current()
    with pytest.raises(ValueError):
        hardware.edit(initial['circuit'],{'kind':'connect','a':endpoint('sensor','ECHO'),'b':endpoint('board',bad_pin)})
    assert service.current()==initial

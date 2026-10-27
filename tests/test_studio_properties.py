"""Real typed property proposals and native compilation, no dynamics or AI."""
import copy
import pytest
from engineering.project import identity
from shapebase.examples import create_disposable_arm


def test_dimension_review_regenerates_geometry_frames_native_proxy_without_head_commit(tmp_path,monkeypatch):
    service,_=create_disposable_arm(tmp_path/'author_arm');p=service.current();before=(service.root/'head.json').read_bytes()
    def forbidden(*a,**kw):raise AssertionError('Property review must not run dynamics')
    monkeypatch.setattr('world.simulation.run',forbidden)
    ops=[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':.42}]
    q=service.propose(identity(p),p['revision'],ops,'Explicit local inspector dimension review',origin='EXPLICIT_LOCAL_USER_REVIEW')
    assert q['operations']==ops and q['approval_status']=='PROPOSED_NOT_APPLIED'
    assert q['validation']['world']=='VALID_COMPILED' and 'NOT_RUN' in q['validation']['simulation']
    s=next(s for s in q['proposed_project']['shape_specs'] if s['id']=='shape_link_one')
    assert s['parameters']['length_m']==.42 and [h['id'] for h in s['mounting_holes']]==['mount_a','mount_b']
    old=next(o for o in p['world']['objects'] if o['id']=='elbow');new=next(o for o in q['proposed_project']['world']['objects'] if o['id']=='elbow')
    assert old['position_m']!=new['position_m'];assert new['parent']==old['parent']=='link_one'
    proxy=next(o for o in q['proposed_project']['world']['objects'] if o['id']=='link_one');assert proxy['dimensions_m'][0]==.42
    assert before==(service.root/'head.json').read_bytes() and service.current()==p
    # Discarding the local UI review means no decide call and no authoritative change.
    assert not list((service.root/'decisions').glob(q['proposal_id']))


@pytest.mark.parametrize('ops',[
 [{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':-.01}],
 [{'kind':'update_shape_parameter','target':'link_one','parameter':'length_m','value':.42}],
 [{'kind':'move_object','target':'link_one','position_m':[.1,0,0]}],
 [{'kind':'move_object','target':'elbow','position_m':[.1,0,0]}],
 [{'kind':'set_mass','target':'link_one','mass_kg':.2}],
 [{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'width_m','value':.001}],
])
def test_invalid_dimensions_wrong_id_and_constrained_transforms_stay_rejected(tmp_path,ops):
    service,_=create_disposable_arm(tmp_path/'arm');p=service.current();before=(service.root/'head.json').read_bytes()
    with pytest.raises(ValueError):service.propose(identity(p),p['revision'],ops,'Invalid property review must fail')
    assert before==(service.root/'head.json').read_bytes() and service.current()==p


def test_old_property_draft_and_review_cannot_apply_to_changed_head(tmp_path):
    service,_=create_disposable_arm(tmp_path/'arm');p=service.current();ops=[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':.42}]
    q=service.propose(identity(p),p['revision'],ops,'Review only')
    # An explicit unrelated local fixture edit makes the saved proposal stale.
    service.edit(identity(p),p['revision'],[{'kind':'rename_object','target':'arm_base','name':'Renamed base'}]);head=service.current()
    with pytest.raises(ValueError,match='Stale'):service.propose(identity(p),p['revision'],ops,'Stale draft')
    with pytest.raises(ValueError,match='Stale'):service.decide(identity(head),head['revision'],q['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
    assert service.current()==head

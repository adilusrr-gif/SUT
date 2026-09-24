from types import SimpleNamespace
import pytest
from app.services.optimizer import OptFeed, optimize, nutrient_totals
from app.core.db import Base, engine, SessionLocal
from app.core.config import settings
from app.main import app
from app.models.entities import OptimizationSnapshot
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer '+settings.app_access_token.get_secret_value()
        yield c

@pytest.mark.parametrize('field,value', [('cp_pct',19.2),('ndf_pct',38.2),('starch_pct',30.2),('fat_pct',6.1)])
def test_actual_dry_matter_upper_bounds(field,value):
    group=SimpleNamespace(target_dmi_kg=22,min_cp_pct=0,max_cp_pct=19,min_ndf_pct=0,max_ndf_pct=38,max_starch_pct=30,max_fat_pct=6,min_me_mcal_per_kg_dm=1,min_ca_pct=0,min_p_pct=0,transition_limit_pct=20)
    feed=OptFeed(1,'boundary',100,0,0,0,0,2,0,0,1,0,50)
    setattr(feed,field,value)
    assert optimize(group,[feed],{1:22})['status']=='infeasible'

@pytest.mark.parametrize('change',['ration','feed','group','legacy'])
def test_stale_apply_preserves_ration(client,change):
    run=client.post('/api/optimize/1').json()
    if change=='ration':
        assert client.put('/api/ration/1',json={'lines':[{'feed_id':1,'kg_as_fed':25}]}).status_code==200
    elif change=='feed':
        feed=client.get('/api/feeds').json()[0];feed['price_kzt_per_kg']+=1
        assert client.put('/api/feeds/1',json=feed).status_code==200
    elif change=='group':
        group=client.get('/api/groups').json()[0];group['cow_count']+=1
        assert client.put('/api/groups/1',json=group).status_code==200
    else:
        with SessionLocal() as db:
            db.delete(db.get(OptimizationSnapshot,run['id']));db.commit()
    before=client.get('/api/ration/1').json()
    assert client.post(f"/api/optimization/{run['id']}/apply").status_code==409
    assert client.get('/api/ration/1').json()==before

def test_apply_idempotent_and_saved_quantities_match_cost(client):
    run=client.post('/api/optimize/1').json()
    prices={str(x['id']):x['price_kzt_per_kg'] for x in client.get('/api/feeds').json()}
    assert round(sum(prices[k]*v for k,v in run['proposed_json'].items()),2)==run['after_cost_kzt']
    path=f"/api/optimization/{run['id']}/apply"
    assert client.post(path).json()['status']=='applied'
    before=client.get('/api/ration/1').json()
    assert client.post(path).json()['status']=='already_applied'
    assert client.get('/api/ration/1').json()==before

def test_invalid_ration_and_feed_update_are_atomic(client):
    before=client.get('/api/ration/1').json()
    assert client.put('/api/ration/1',json={'lines':[{'feed_id':1,'kg_as_fed':10}]*2}).status_code==422
    assert client.get('/api/ration/1').json()==before
    feed=client.get('/api/feeds').json()[0];feed['min_as_fed_kg']=feed['max_as_fed_kg']+1
    assert client.put('/api/feeds/1',json=feed).status_code==422

def test_inactive_current_feed_is_not_silently_omitted(client):
    feed=client.get('/api/feeds').json()[0];feed['active']=False
    assert client.put('/api/feeds/1',json=feed).status_code==200
    assert client.post('/api/optimize/1').status_code==422

def test_empty_and_incompatible_bounds():
    group=SimpleNamespace(target_dmi_kg=22,min_cp_pct=0,max_cp_pct=100,min_ndf_pct=0,max_ndf_pct=100,max_starch_pct=100,max_fat_pct=100,min_me_mcal_per_kg_dm=0,min_ca_pct=0,min_p_pct=0,transition_limit_pct=20)
    assert optimize(group,[],{})['status']=='infeasible'
    assert optimize(group,[OptFeed(1,'bad',100,0,0,0,0,2,0,0,1,5,50)],{})['status']=='infeasible'

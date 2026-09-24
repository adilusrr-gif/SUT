from datetime import date, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.db import Base, engine, SessionLocal
from app.core.config import settings
from app.models.entities import EconomicsEntry
from sqlalchemy import select

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer '+settings.app_access_token.get_secret_value()
        yield c

def body(day='2026-01-01',**kw):
    return dict(day=day,cow_count=100,feed_cost_kzt='1000.00',milk_revenue_kzt='2000.00',other_cost_kzt='0.00',source='Daily worksheet 1',expected_revision=0,request_id=str(uuid4()),**kw)

def put(c,p):return c.post('/api/economics/1/entries',json=p)
def compare(c):return c.post('/api/economics/1/compare',json={'before_start':'2026-01-01','before_end':'2026-01-07','after_start':'2026-01-08','after_end':'2026-01-14'})

def test_append_correction_and_idempotent_retry(client):
    p=body();r=put(client,p);assert r.status_code==200
    assert put(client,p).json()['id']==r.json()['id']
    q={**p,'request_id':str(uuid4()),'expected_revision':1,'feed_cost_kzt':'900.00','correction_reason':'Corrected invoice'}
    assert put(client,q).json()['revision']==2
    hist=client.get('/api/economics/1/history/2026-01-01').json()
    assert [x['feed_cost_kzt'] for x in hist]==['1000.00','900.00']
    assert put(client,{**q,'request_id':str(uuid4())}).status_code==409
    assert put(client,{**p,'feed_cost_kzt':'1.00'}).status_code==409
    with SessionLocal() as db: assert len(db.scalars(select(EconomicsEntry)).all())==2

def test_comparison_normalizes_cow_days_not_calendar_and_no_double_count(client):
    assert put(client,body()).status_code==200
    after=body('2026-01-08');after.update(cow_count=200,feed_cost_kzt='1800.00',milk_revenue_kzt='4200.00',other_cost_kzt='50.00')
    assert put(client,after).status_code==200
    result=compare(client).json()
    assert result['before']['days_recorded']==1 and result['before']['days_expected']==7
    assert result['after']['cow_days']==200
    assert result['effect']=={'feed_savings_kzt':'200.00','milk_revenue_change_kzt':'200.00','margin_change_kzt':'400.00','other_cost_change_kzt':'50.00','net_change_entered_costs_kzt':'350.00'}

def test_missing_data_is_not_zero_effect(client):
    assert compare(client).json()['effect'] is None
    put(client,body())
    assert compare(client).json()['effect'] is None

def test_losses_and_correction_propagate(client):
    put(client,body());p=body('2026-01-08');p['milk_revenue_kzt']='1800.00';put(client,p)
    assert compare(client).json()['effect']['margin_change_kzt']=='-200.00'
    p.update(request_id=str(uuid4()),expected_revision=1,correction_reason='Reconciled',milk_revenue_kzt='2100.00');put(client,p)
    assert compare(client).json()['effect']['margin_change_kzt']=='100.00'
    assert compare(client).json()['after']['days_recorded']==1

@pytest.mark.parametrize('field,value',[('feed_cost_kzt','-1'),('milk_revenue_kzt','NaN'),('other_cost_kzt','0.001'),('cow_count',0),('source','  '),('day','2999-01-01')])
def test_bad_data_rejected(client,field,value):
    p=body();p[field]=value
    assert put(client,p).status_code==422
    assert client.get('/api/economics/1/history/2026-01-01').json()==[]

def test_bad_periods_and_auth(client):
    assert client.post('/api/economics/1/compare',json={'before_start':'2026-01-01','before_end':'2026-01-08','after_start':'2026-01-08','after_end':'2026-01-14'}).status_code==422
    assert client.get('/api/economics/1/entries?start=2026-02-01&end=2026-01-01').status_code==422
    assert client.post('/api/economics/999/entries',json=body()).status_code==404
    client.headers.pop('Authorization')
    assert put(client,body()).status_code==401
    assert client.get('/api/economics/1/history/2026-01-01').status_code==401

def test_catalog_changes_do_not_reprice_ledger(client):
    put(client,body());put(client,body('2026-01-08'));before=compare(client).json()
    f=client.get('/api/feeds').json()[0];f['price_kzt_per_kg']*=2;client.put('/api/feeds/1',json=f)
    g=client.get('/api/groups').json()[0];g['cow_count']+=10;client.put('/api/groups/1',json=g)
    assert compare(client).json()==before

def test_fresh_setup_flow_without_demo(monkeypatch):
    Base.metadata.drop_all(engine);monkeypatch.setattr(settings,'demo_seed',False)
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer '+settings.app_access_token.get_secret_value()
        assert c.get('/api/groups').json()==[]
        f=c.put('/api/farm',json={'name':'Pilot','herd_size':200,'milk_price_kzt':250});assert f.status_code==200
        g=c.post('/api/groups',json={'farm_id':f.json()['id'],'name':'Pilot group','cow_count':100,'body_weight_kg':650,'milk_yield_l':30,'target_dmi_kg':22});assert g.status_code==200
        assert c.get('/api/dashboard/'+str(g.json()['id'])).status_code==200

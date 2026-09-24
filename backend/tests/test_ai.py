import json
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.main import app
from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.services import ai

@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(engine)
    monkeypatch.setattr(settings,'openai_api_key',SecretStr('test-not-a-live-key'))
    monkeypatch.setattr(settings,'llm_provider','openai')
    monkeypatch.setattr(settings,'llm_daily_call_limit',100)
    with TestClient(app) as client:
        client.headers['Authorization']='Bearer '+settings.app_access_token.get_secret_value()
        yield client

@pytest.fixture
def run_id(client):
    r=client.post('/api/optimize/1')
    assert r.status_code==200,r.text
    return r.json()['id']

def wire(monkeypatch, handler):
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))

def completed(focus='cost'):
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'focus':focus})}]}], 'usage':{'input_tokens':20,'output_tokens':8,'total_tokens':28}}

def test_openai_wire_cache_and_math(client,run_id,monkeypatch):
    requests=[]
    def handler(req):
        requests.append(req)
        body=json.loads(req.content)
        assert str(req.url)=='https://api.openai.com/v1/responses'
        assert body['store'] is False and body['max_output_tokens']==128
        assert body['text']['format']['strict'] is True
        assert body['text']['format']['schema']['additionalProperties'] is False
        assert req.headers['Authorization']=='Bearer test-not-a-live-key'
        assert set(json.loads(body['input'][1]['content']))=={'changes_count','savings_positive','has_warnings'}
        return httpx.Response(200,json=completed())
    wire(monkeypatch,handler)
    before=client.get('/api/optimization/latest/1').json()
    a=client.post(f'/api/ai/explain/{run_id}').json()
    b=client.post(f'/api/ai/explain/{run_id}').json()
    assert a['source']=='llm_constrained' and not a['cached']
    assert b['cached'] and len(requests)==1 and a['text']==b['text']
    assert f"{before['savings_per_cow_day_kzt']:.2f}" in a['text']
    assert client.get('/api/optimization/latest/1').json()==before
    assert client.get('/api/ai/status').json()['calls_today']==1
    assert a['usage']['total_tokens']==28

@pytest.mark.parametrize('failure',['401','429','500','timeout','refusal','incomplete','invalid','extra'])
def test_provider_failures_do_not_break_math(client,run_id,monkeypatch,failure):
    def handler(req):
        if failure.isdigit():return httpx.Response(int(failure),json={'error':'provider-private-error'})
        if failure=='timeout':raise httpx.ReadTimeout('private-error')
        if failure=='refusal':return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]})
        if failure=='incomplete':return httpx.Response(200,json={'status':'incomplete','output':[]})
        data=completed('invented' if failure=='invalid' else 'cost')
        if failure=='extra':data['output'][0]['content'][0]['text']='{"focus":"cost","savings":999999}'
        return httpx.Response(200,json=data)
    wire(monkeypatch,handler)
    r=client.post(f'/api/ai/explain/{run_id}')
    assert r.status_code==200 and r.json()['source']=='template_fallback'
    assert 'private-error' not in r.text and '999999' not in r.text
    assert client.post('/api/optimize/1').status_code==200

def test_daily_limit_counts_failed_attempts(client,run_id,monkeypatch):
    monkeypatch.setattr(settings,'llm_daily_call_limit',1)
    calls=[]
    def handler(req):calls.append(1);return httpx.Response(429)
    wire(monkeypatch,handler)
    assert client.post(f'/api/ai/explain/{run_id}').json()['reason']=='provider_unavailable_or_invalid'
    assert client.post(f'/api/ai/explain/{run_id}').json()['reason']=='daily_limit'
    assert len(calls)==1
    with SessionLocal() as db:assert not ai.reserve_call(db)

def test_disabled_and_missing_key_never_call_network(client,run_id,monkeypatch):
    def forbidden(req):raise AssertionError('Unexpected paid call')
    wire(monkeypatch,forbidden)
    monkeypatch.setattr(settings,'openai_api_key',SecretStr(''))
    assert client.post(f'/api/ai/explain/{run_id}').json()['reason']=='not_configured'
    monkeypatch.setattr(settings,'llm_provider','disabled')
    assert client.post(f'/api/ai/explain/{run_id}').json()['source']=='template_fallback'
    assert client.get('/api/ai/status').json()['calls_today']==0

def test_auth_blocks_farm_and_paid_calls(client,run_id):
    client.headers.pop('Authorization')
    for path in ['/api/farm','/api/groups','/api/ai/status']:
        assert client.get(path).status_code==401
    assert client.post(f'/api/ai/explain/{run_id}').status_code==401
    assert client.get('/api/health').status_code==200
    assert client.get('/docs').status_code==404

def test_status_no_secrets_or_false_connectivity(client):
    r=client.get('/api/ai/status')
    assert r.json()['configured'] and not r.json()['connection_verified']
    assert 'test-not-a-live-key' not in r.text

def test_ollama_remains_available(client,run_id,monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','ollama')
    def handler(req):
        assert req.url.path=='/api/chat' and 'authorization' not in req.headers
        return httpx.Response(200,json={'message':{'content':'{"focus":"constraints"}'}})
    wire(monkeypatch,handler)
    r=client.post(f'/api/ai/explain/{run_id}').json()
    assert r['source']=='llm_constrained' and r['provider']=='ollama'

def test_malformed_response_falls_back(client,run_id,monkeypatch):
    wire(monkeypatch,lambda req:httpx.Response(200,json=['unexpected']))
    assert client.post(f'/api/ai/explain/{run_id}').json()['source']=='template_fallback'


def test_atomic_budget_across_sessions(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(settings,'llm_daily_call_limit',3)
    def reserve(_):
        with SessionLocal() as db:return ai.reserve_call(db)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(reserve,range(12)))
    assert sum(results)==3

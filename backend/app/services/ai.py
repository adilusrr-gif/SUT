"""Only an enum crosses the LLM trust boundary; all quantities are rendered by code."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import AIExplanation, AIDailyUsage

PROMPT_VERSION = 'sut-focus-2.1'

class Focus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    focus: Literal['cost', 'constraints', 'data_quality']


def status(db: Session):
    configured = (bool(settings.openai_api_key.get_secret_value()) and bool(settings.openai_model)) if settings.llm_provider == 'openai' else bool(settings.ollama_url and settings.ollama_model) if settings.llm_provider == 'ollama' else False
    usage = db.get(AIDailyUsage, datetime.now(timezone.utc).date())
    return {'provider': settings.llm_provider, 'model': model_name(), 'configured': configured,
            'connection_verified': False, 'calls_today': usage.calls if usage else 0,
            'daily_call_limit': settings.llm_daily_call_limit}


def model_name():
    return settings.openai_model if settings.llm_provider == 'openai' else settings.ollama_model if settings.llm_provider == 'ollama' else None


def reserve_call(db: Session) -> bool:
    """Atomic conditional UPDATE prevents exceeding quota across workers/restarts."""
    today = datetime.now(timezone.utc).date()
    if not db.get(AIDailyUsage, today):
        db.add(AIDailyUsage(day=today, calls=0))
        try: db.commit()
        except IntegrityError: db.rollback()
    changed = db.execute(update(AIDailyUsage).where(AIDailyUsage.day == today, AIDailyUsage.calls < settings.llm_daily_call_limit).values(calls=AIDailyUsage.calls + 1))
    db.commit()
    return changed.rowcount == 1


def render(payload, focus):
    lead = {'cost': 'Сравниваем стоимость введённого и расчётного рационов.',
            'constraints': 'Результат относится только к заданным ограничениям питания.',
            'data_quality': 'Проверьте актуальность анализов кормов и введённых ограничений.'}[focus]
    lines = [f"{x['feed']}: {x['before_kg']:.2f} → {x['after_kg']:.2f} кг" for x in payload['changes'][:5]]
    text = lead + '\nЧто меняем:\n' + ('\n'.join(f'{i+1}. {x}' for i,x in enumerate(lines)) or 'Нет изменений более 0,05 кг.')
    text += f"\nРасчётная экономия: {payload['savings_per_cow_day_kzt']:.2f} ₸/день на корову; {payload['savings_group_month_kzt']:.2f} ₸ за 30 дней на группу."
    text += '\nЭто потенциал, а не полученная прибыль. Рост удоя не прогнозируется. Подтвердите рацион у зоотехника перед внедрением.'
    return text


async def choose_focus(payload):
    # No names, identifiers or full ration are sent to the external model.
    facts = {'changes_count': len(payload['changes']),
             'savings_positive': payload['savings_per_cow_day_kzt'] > 0,
             'has_warnings': bool(payload.get('warnings'))}
    messages = [{'role':'system','content':'Select an explanation focus for a feed-ration calculation. Do not calculate or prescribe. Return JSON with focus: cost, constraints, or data_quality.'},
                {'role':'user','content':json.dumps(facts)}]
    if settings.llm_provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        body = {'model':settings.openai_model, 'input':messages, 'store':False,
                'max_output_tokens':settings.llm_max_output_tokens,
                'text':{'format':{'type':'json_schema','name':'explanation_focus','strict':True,'schema':Focus.model_json_schema()}}}
        headers = {'Authorization':'Bearer ' + settings.openai_api_key.get_secret_value()}
    else:
        url = settings.ollama_url.rstrip('/') + '/api/chat'
        body = {'model':settings.ollama_model,'messages':messages,'stream':False,
                'format':Focus.model_json_schema(), 'options':{'temperature':0,'num_predict':settings.llm_max_output_tokens}}
        headers = {}
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds, follow_redirects=False, trust_env=False) as client:
        response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()
    if settings.llm_provider == 'openai':
        if data.get('status') != 'completed': raise ValueError('incomplete')
        content=[]
        for item in data.get('output', []):
            if item.get('type') == 'message':
                for part in item.get('content', []):
                    if part.get('type') == 'refusal': raise ValueError('refusal')
                    if part.get('type') == 'output_text': content.append(part['text'])
        text = ''.join(content)
        usage = {k:v for k,v in data.get('usage', {}).items() if k in ('input_tokens','output_tokens','total_tokens') and isinstance(v,int) and v >= 0}
    else:
        text = data['message']['content']
        usage = {k:v for k,v in {'input_tokens':data.get('prompt_eval_count'), 'output_tokens':data.get('eval_count')}.items() if isinstance(v,int) and v >= 0}
    return Focus.model_validate_json(text).focus, usage


async def explain(payload, db: Session):
    key = hashlib.sha256(json.dumps([PROMPT_VERSION,settings.llm_provider,model_name(),payload],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    cached = db.get(AIExplanation,key)
    if cached: return {**cached.response_json,'cached':True}
    reason = None
    if not status(db)['configured']: reason='not_configured'
    elif not reserve_call(db): reason='daily_limit'
    if reason is None:
        try:
            focus, usage = await choose_focus(payload)
            result = {'text':render(payload,focus),'model':model_name(),'provider':settings.llm_provider,
                      'source':'llm_constrained','usage':usage,'cached':False,'reason':None}
            db.add(AIExplanation(cache_key=key,response_json=result))
            try: db.commit()
            except IntegrityError:
                db.rollback()
                other=db.get(AIExplanation,key)
                if other: return {**other.response_json,'cached':True}
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            reason='provider_unavailable_or_invalid'
    return {'text':render(payload,'data_quality' if payload.get('warnings') else 'cost'),
            'model':None,'provider':settings.llm_provider,'source':'template_fallback',
            'usage':{},'cached':False,'reason':reason}

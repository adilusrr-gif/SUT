"""Daily evidence ledger. Currency calculations use Decimal, never binary floats."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import authorize
from app.core.db import get_db
from app.models.entities import CowGroup, EconomicsEntry
from app.schemas.dto import InputModel
from app.api.routes import lock_farm

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
class EntryIn(InputModel):
    day: date
    cow_count: int = Field(ge=1, le=100000)
    feed_cost_kzt: Money
    milk_revenue_kzt: Money
    other_cost_kzt: Money = Decimal('0')
    source: str = Field(min_length=1, max_length=500)
    correction_reason: str = Field(default='', max_length=500)
    expected_revision: int = Field(ge=0)
    request_id: UUID

    @model_validator(mode='after')
    def validate_evidence(self):
        if self.day > date.today(): raise ValueError('Фактическая запись не может быть в будущем')
        if not self.source.strip(): raise ValueError('Источник обязателен')
        if self.expected_revision and not self.correction_reason.strip():
            raise ValueError('Укажите причину исправления')
        return self

class Periods(InputModel):
    before_start: date
    before_end: date
    after_start: date
    after_end: date
    @model_validator(mode='after')
    def validate_periods(self):
        if not self.before_start <= self.before_end < self.after_start <= self.after_end:
            raise ValueError('Периоды должны идти последовательно и не пересекаться')
        if (self.after_end-self.before_start).days > 730:
            raise ValueError('Диапазон не больше 731 дня')
        return self

router = APIRouter(prefix='/api/economics', dependencies=[Depends(authorize)])

def group_exists(db, group_id):
    if not db.get(CowGroup, group_id): raise HTTPException(404, 'Group not found')

def serialize(row):
    return {'id':row.id,'group_id':row.group_id,'revision':row.revision,
            'created_at':row.created_at, **row.payload_json}

def latest_rows(db, group_id, start, end):
    rows=db.scalars(select(EconomicsEntry).where(EconomicsEntry.group_id==group_id,
        EconomicsEntry.day>=start, EconomicsEntry.day<=end).order_by(EconomicsEntry.day, EconomicsEntry.revision)).all()
    return list({r.day:r for r in rows}.values())

@router.post('/{group_id}/entries')
def record(group_id:int, payload:EntryIn, db:Session=Depends(get_db)):
    lock_farm(db)
    group_exists(db,group_id)
    body=payload.model_dump(mode='json')
    existing=db.scalar(select(EconomicsEntry).where(EconomicsEntry.request_id==str(payload.request_id)))
    if existing:
        if existing.group_id!=group_id or existing.payload_json!=body:
            raise HTTPException(409,'Идентификатор запроса уже использован для другой записи')
        return serialize(existing)
    latest=db.scalar(select(EconomicsEntry).where(EconomicsEntry.group_id==group_id,EconomicsEntry.day==payload.day).order_by(EconomicsEntry.revision.desc()).limit(1))
    if (latest.revision if latest else 0)!=payload.expected_revision:
        raise HTTPException(409,'Запись изменена. Загрузите актуальную версию перед исправлением')
    row=EconomicsEntry(group_id=group_id,day=payload.day,revision=payload.expected_revision+1,
                      request_id=str(payload.request_id),payload_json=body)
    db.add(row)
    try: db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Конкурирующая запись. Обновите журнал')
    db.refresh(row)
    return serialize(row)

@router.get('/{group_id}/entries')
def entries(group_id:int,start:date,end:date,db:Session=Depends(get_db)):
    group_exists(db,group_id)
    if end<start or (end-start).days>730: raise HTTPException(422,'Недопустимый период')
    return [serialize(r) for r in latest_rows(db,group_id,start,end)]

@router.get('/{group_id}/history/{day}')
def history(group_id:int,day:date,db:Session=Depends(get_db)):
    group_exists(db,group_id)
    rows=db.scalars(select(EconomicsEntry).where(EconomicsEntry.group_id==group_id,EconomicsEntry.day==day).order_by(EconomicsEntry.revision)).all()
    return [serialize(r) for r in rows]

def money(value):
    return str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def summarize(rows,start,end):
    cows=sum(r.payload_json['cow_count'] for r in rows)
    totals={k:sum((Decimal(r.payload_json[k]) for r in rows),Decimal(0)) for k in ['feed_cost_kzt','milk_revenue_kzt','other_cost_kzt']}
    totals['margin_over_feed_kzt']=totals['milk_revenue_kzt']-totals['feed_cost_kzt']
    totals['margin_after_entered_costs_kzt']=totals['margin_over_feed_kzt']-totals['other_cost_kzt']
    return {'start':start,'end':end,'days_recorded':len(rows),'days_expected':(end-start).days+1,
            'cow_days':cows,'totals':{k:money(v) for k,v in totals.items()},
            'per_cow_day':{k:money(v/cows) for k,v in totals.items()} if cows else None},totals

@router.post('/{group_id}/compare')
def compare(group_id:int,payload:Periods,db:Session=Depends(get_db)):
    group_exists(db,group_id)
    # One SELECT gives a consistent revision view for both periods.
    rows=latest_rows(db,group_id,payload.before_start,payload.after_end)
    before,b=summarize([r for r in rows if r.day<=payload.before_end],payload.before_start,payload.before_end)
    after,a=summarize([r for r in rows if r.day>=payload.after_start],payload.after_start,payload.after_end)
    effect=None
    if before['cow_days'] and after['cow_days']:
        scale=Decimal(after['cow_days'])/Decimal(before['cow_days'])
        feed=b['feed_cost_kzt']*scale-a['feed_cost_kzt']
        revenue=a['milk_revenue_kzt']-b['milk_revenue_kzt']*scale
        other=a['other_cost_kzt']-b['other_cost_kzt']*scale
        effect={'feed_savings_kzt':money(feed),'milk_revenue_change_kzt':money(revenue),
                'margin_change_kzt':money(feed+revenue),'other_cost_change_kzt':money(other),
                'net_change_entered_costs_kzt':money(feed+revenue-other)}
    return {'before':before,'after':after,'effect':effect,
            'basis':'baseline_per_cow_day_scaled_to_after_observed_cow_days',
            'note':'По введённым данным. Пропуски не заполнены. Сравнительный эффект не доказывает причинный эффект программы и не является чистой прибылью.'}

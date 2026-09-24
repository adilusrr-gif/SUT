from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.entities import Farm, CowGroup, Feed, RationLine, OptimizationRun, Observation, OptimizationSnapshot
from app.schemas.dto import FarmIn, GroupIn, FeedIn, RationIn, ObservationIn
from app.services.optimizer import OptFeed, optimize
from app.services import ai
from app.core.auth import authorize

router = APIRouter(prefix="/api", dependencies=[Depends(authorize)])


def obj_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def lock_farm(db):
    # One-farm pilot: serialize catalog/ration/constraint writes in PostgreSQL.
    return db.scalar(select(Farm).order_by(Farm.id).limit(1).with_for_update())


def input_snapshot(db, group):
    feeds = db.scalars(select(Feed).order_by(Feed.id)).all()
    ration = db.scalars(select(RationLine).where(RationLine.group_id == group.id).order_by(RationLine.feed_id)).all()
    return {'group': obj_dict(group), 'feeds': [obj_dict(f) for f in feeds],
            'ration': {str(x.feed_id): x.kg_as_fed for x in ration}}


@router.get("/farm")
def get_farm(db: Session = Depends(get_db)):
    farm = db.scalar(select(Farm).limit(1))
    if not farm:
        raise HTTPException(404, "Farm not found")
    return obj_dict(farm)


@router.put("/farm")
def update_farm(payload: FarmIn, db: Session = Depends(get_db)):
    farm = db.scalar(select(Farm).limit(1))
    if not farm:
        farm = Farm()
        db.add(farm)
    for k, v in payload.model_dump().items():
        setattr(farm, k, v)
    db.commit(); db.refresh(farm)
    return obj_dict(farm)


@router.get("/groups")
def groups(db: Session = Depends(get_db)):
    return [obj_dict(x) for x in db.scalars(select(CowGroup).order_by(CowGroup.id)).all()]


@router.post("/groups")
def create_group(payload: GroupIn, db: Session = Depends(get_db)):
    if not db.get(Farm, payload.farm_id): raise HTTPException(422, "Unknown farm_id")
    row = CowGroup(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return obj_dict(row)


@router.put("/groups/{group_id}")
def update_group(group_id: int, payload: GroupIn, db: Session = Depends(get_db)):
    lock_farm(db)
    if not db.get(Farm, payload.farm_id): raise HTTPException(422, "Unknown farm_id")
    row = db.get(CowGroup, group_id)
    if not row: raise HTTPException(404, "Group not found")
    for k, v in payload.model_dump().items(): setattr(row, k, v)
    db.commit(); db.refresh(row)
    return obj_dict(row)


@router.get("/feeds")
def feeds(db: Session = Depends(get_db)):
    return [obj_dict(x) for x in db.scalars(select(Feed).order_by(Feed.id)).all()]


@router.post("/feeds")
def create_feed(payload: FeedIn, db: Session = Depends(get_db)):
    lock_farm(db)
    if payload.min_as_fed_kg > payload.max_as_fed_kg:
        raise HTTPException(422, "min_as_fed_kg must be <= max_as_fed_kg")
    row = Feed(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return obj_dict(row)


@router.put("/feeds/{feed_id}")
def update_feed(feed_id: int, payload: FeedIn, db: Session = Depends(get_db)):
    lock_farm(db)
    row = db.get(Feed, feed_id)
    if not row: raise HTTPException(404, "Feed not found")
    for k, v in payload.model_dump().items(): setattr(row, k, v)
    db.commit(); db.refresh(row)
    return obj_dict(row)


@router.get("/ration/{group_id}")
def get_ration(group_id: int, db: Session = Depends(get_db)):
    lines = db.scalars(select(RationLine).where(RationLine.group_id == group_id)).all()
    feeds_map = {f.id: f for f in db.scalars(select(Feed).join(RationLine, RationLine.feed_id == Feed.id).where(RationLine.group_id == group_id)).all()}
    return [
        {"feed_id": x.feed_id, "feed_name": feeds_map[x.feed_id].name if x.feed_id in feeds_map else str(x.feed_id), "kg_as_fed": x.kg_as_fed}
        for x in lines
    ]


@router.put("/ration/{group_id}")
def put_ration(group_id: int, payload: RationIn, db: Session = Depends(get_db)):
    lock_farm(db)
    if not db.get(CowGroup, group_id): raise HTTPException(404, "Group not found")
    feed_ids = {f.id for f in db.scalars(select(Feed)).all()}
    for line in payload.lines:
        if line.feed_id not in feed_ids: raise HTTPException(422, f"Unknown feed_id {line.feed_id}")
    db.execute(delete(RationLine).where(RationLine.group_id == group_id))
    for line in payload.lines:
        if line.kg_as_fed > 0:
            db.add(RationLine(group_id=group_id, feed_id=line.feed_id, kg_as_fed=line.kg_as_fed))
    db.commit()
    return get_ration(group_id, db)


@router.post("/optimize/{group_id}")
def run_opt(group_id: int, db: Session = Depends(get_db)):
    lock_farm(db)
    group = db.get(CowGroup, group_id)
    if not group: raise HTTPException(404, "Group not found")
    feed_rows = db.scalars(select(Feed).where(Feed.active.is_(True)).order_by(Feed.id)).all()
    current_rows = db.scalars(select(RationLine).where(RationLine.group_id == group_id)).all()
    current = {x.feed_id: x.kg_as_fed for x in current_rows}
    if set(current) - {f.id for f in feed_rows}:
        raise HTTPException(422, "Текущий рацион содержит неактивный корм. Сначала проверьте рацион и доступность кормов.")
    snapshot = input_snapshot(db, group)
    opt_feeds = [OptFeed(**{k: getattr(f, k) for k in OptFeed.__dataclass_fields__}) for f in feed_rows]
    result = optimize(group, opt_feeds, current)
    if result["status"] != "ok":
        raise HTTPException(422, result)
    run = OptimizationRun(
        group_id=group_id,
        status="ok",
        before_cost_kzt=result["before_cost_kzt"],
        after_cost_kzt=result["after_cost_kzt"],
        savings_per_cow_day_kzt=result["savings_per_cow_day_kzt"],
        savings_group_month_kzt=round(result["savings_per_cow_day_kzt"] * group.cow_count * 30, 2),
        before_json=result["before"], proposed_json=result["proposed"], nutrients_json=result["nutrients"], warnings_json=result["warnings"]
    )
    db.add(run); db.flush()
    db.add(OptimizationSnapshot(run_id=run.id, inputs_json=snapshot))
    db.commit(); db.refresh(run)
    return {**obj_dict(run), "feeds": {str(f.id): f.name for f in feed_rows}}


@router.get("/optimization/latest/{group_id}")
def latest_opt(group_id: int, db: Session = Depends(get_db)):
    row = db.scalar(select(OptimizationRun).where(OptimizationRun.group_id == group_id).order_by(OptimizationRun.id.desc()).limit(1))
    return obj_dict(row) if row else None


@router.post("/optimization/{run_id}/apply")
def apply_opt(run_id: int, db: Session = Depends(get_db)):
    lock_farm(db)
    run = db.get(OptimizationRun, run_id)
    if not run: raise HTTPException(404, "Optimization run not found")
    if run.applied_at:
        return {"status": "already_applied", "run_id": run_id}
    snapshot = db.get(OptimizationSnapshot, run_id)
    group = db.get(CowGroup, run.group_id)
    if run.status != 'ok' or not snapshot or not group or snapshot.inputs_json != input_snapshot(db, group):
        raise HTTPException(409, "Исходные данные изменились или снимок отсутствует. Выполните новый расчёт.")
    db.execute(delete(RationLine).where(RationLine.group_id == run.group_id))
    for feed_id, kg in run.proposed_json.items():
        if float(kg) > 0:
            db.add(RationLine(group_id=run.group_id, feed_id=int(feed_id), kg_as_fed=float(kg)))
    run.applied_at = datetime.utcnow()
    db.commit()
    return {"status": "applied", "run_id": run_id, "warning": "Перед фактическим внедрением подтвердите рацион у зоотехника."}


@router.get("/observations/{group_id}")
def observations(group_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Observation).where(Observation.group_id == group_id).order_by(Observation.observed_on.desc()).limit(90)).all()
    return [obj_dict(x) for x in rows]


@router.post("/observations")
def add_observation(payload: ObservationIn, db: Session = Depends(get_db)):
    if not db.get(CowGroup, payload.group_id): raise HTTPException(404, "Group not found")
    existing = db.scalar(select(Observation).where(Observation.group_id == payload.group_id, Observation.observed_on == payload.observed_on))
    if existing:
        for k, v in payload.model_dump().items(): setattr(existing, k, v)
        row = existing
    else:
        row = Observation(**payload.model_dump()); db.add(row)
    db.commit(); db.refresh(row)
    return obj_dict(row)


@router.get("/dashboard/{group_id}")
def dashboard(group_id: int, db: Session = Depends(get_db)):
    group = db.get(CowGroup, group_id)
    farm = db.scalar(select(Farm).limit(1))
    if not group or not farm: raise HTTPException(404, "Farm/group not found")
    feeds_map = {f.id: f for f in db.scalars(select(Feed).join(RationLine, RationLine.feed_id == Feed.id).where(RationLine.group_id == group_id)).all()}
    ration = db.scalars(select(RationLine).where(RationLine.group_id == group_id)).all()
    feed_cost = sum(x.kg_as_fed * feeds_map[x.feed_id].price_kzt_per_kg for x in ration if x.feed_id in feeds_map)
    milk_revenue = group.milk_yield_l * farm.milk_price_kzt
    latest = db.scalar(select(OptimizationRun).where(OptimizationRun.group_id == group_id).order_by(OptimizationRun.id.desc()).limit(1))
    obs = db.scalars(select(Observation).where(Observation.group_id == group_id).order_by(Observation.observed_on.desc()).limit(30)).all()
    return {
        "group": obj_dict(group), "farm": obj_dict(farm),
        "calculation_basis": "configured_ration_current_prices_and_configured_milk_yield",
        "realized_savings_kzt": None,
        "observed_profit_available": False,
        "current": {
            "feed_cost_per_cow_day_kzt": round(feed_cost, 2),
            "milk_revenue_per_cow_day_kzt": round(milk_revenue, 2),
            "margin_over_feed_per_cow_day_kzt": round(milk_revenue - feed_cost, 2),
            "feed_cost_group_month_kzt": round(feed_cost * group.cow_count * 30, 2),
        },
        "latest_optimization": obj_dict(latest) if latest else None,
        "observations": [obj_dict(x) for x in obs],
        "note": "Маржа над кормом ≠ чистая прибыль: не учтены зарплаты, ветеринария, энергия и прочие расходы."
    }


@router.get("/ai/status")
async def ai_status(db: Session = Depends(get_db)):
    return ai.status(db)


@router.post("/ai/explain/{run_id}")
async def ai_explain(run_id: int, db: Session = Depends(get_db)):
    run = db.get(OptimizationRun, run_id)
    if not run: raise HTTPException(404, "Optimization run not found")
    group = db.get(CowGroup, run.group_id)
    feeds_map = {f.id: f.name for f in db.scalars(select(Feed)).all()}
    changes = []
    ids = set(map(int, run.before_json.keys())) | set(map(int, run.proposed_json.keys()))
    for fid in sorted(ids):
        before = float(run.before_json.get(str(fid), run.before_json.get(fid, 0)) or 0)
        after = float(run.proposed_json.get(str(fid), run.proposed_json.get(fid, 0)) or 0)
        if abs(after-before) >= 0.05:
            changes.append({"feed": feeds_map.get(fid, str(fid)), "before_kg": before, "after_kg": after, "delta_kg": round(after-before,3)})
    payload = {
        "changes": changes,
        "savings_per_cow_day_kzt": run.savings_per_cow_day_kzt,
        "savings_group_month_kzt": run.savings_group_month_kzt,
        "group_name": group.name,
        "cow_count": group.cow_count,
        "nutrients": run.nutrients_json,
        "warnings": run.warnings_json,
    }
    return await ai.explain(payload, db)

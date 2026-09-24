from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.models.entities import Farm, CowGroup, Feed, RationLine, Observation
from app.api.routes import router

app = FastAPI(title=settings.app_name, version="2.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


def seed_demo():
    if not settings.demo_seed:
        return
    db = SessionLocal()
    try:
        if db.scalar(select(Farm).limit(1)):
            return
        farm = Farm(name="Demo Dairy Astana", herd_size=200, milk_price_kzt=220)
        db.add(farm); db.flush()
        group = CowGroup(
            farm_id=farm.id, name="Высокоудойные", cow_count=80, body_weight_kg=650,
            milk_yield_l=32, target_dmi_kg=22.0, min_cp_pct=15.5, max_cp_pct=19.0,
            min_ndf_pct=28, max_ndf_pct=38, max_starch_pct=30, max_fat_pct=6.0,
            min_me_mcal_per_kg_dm=2.15, min_ca_pct=0.62, min_p_pct=0.32, transition_limit_pct=20
        )
        db.add(group); db.flush()
        feed_data = [
            ("Кукурузный силос",35,8.0,45,28,3.0,2.25,0.30,0.22,18,12,30),
            ("Люцерновое сено",88,18.0,42,2,2.5,2.05,1.35,0.25,75,1,8),
            ("Ячмень",88,12.0,20,58,2.2,3.05,0.08,0.38,105,0,8),
            ("Соевый шрот",90,48.0,12,3,2.0,2.95,0.30,0.65,245,0,5),
            ("Рапсовый шрот",90,38.0,24,5,3.0,2.65,0.70,1.10,165,0,5),
            ("Минеральный премикс",95,0.0,0,0,0,0.2,18.0,7.0,380,0.15,0.6),
        ]
        feeds = []
        for d in feed_data:
            f = Feed(name=d[0], dm_pct=d[1], cp_pct=d[2], ndf_pct=d[3], starch_pct=d[4], fat_pct=d[5], me_mcal_per_kg_dm=d[6], ca_pct=d[7], p_pct=d[8], price_kzt_per_kg=d[9], min_as_fed_kg=d[10], max_as_fed_kg=d[11], active=True)
            db.add(f); feeds.append(f)
        db.flush()
        ration = {
            "Кукурузный силос": 24.0,
            "Люцерновое сено": 5.0,
            "Ячмень": 5.0,
            "Соевый шрот": 2.5,
            "Рапсовый шрот": 1.2,
            "Минеральный премикс": 0.35,
        }
        for f in feeds:
            db.add(RationLine(group_id=group.id, feed_id=f.id, kg_as_fed=ration[f.name]))
        from datetime import date, timedelta
        today = date.today()
        for i in range(7):
            db.add(Observation(group_id=group.id, observed_on=today-timedelta(days=i), milk_yield_l=32.0 + (i%3-1)*0.3, fat_pct=3.72, protein_pct=3.18, somatic_cells_k=165))
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup():
    if len(settings.app_access_token.get_secret_value()) < 32:
        raise RuntimeError("Set APP_ACCESS_TOKEN to at least 32 random characters")
    Base.metadata.create_all(bind=engine)
    seed_demo()


@app.get("/api/health")
def health():
    return {"status":"ok", "service":"sut-backend", "version":"2.3.0"}

from app.api.economics import router as economics_router
app.include_router(economics_router)

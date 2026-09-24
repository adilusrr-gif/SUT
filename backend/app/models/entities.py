from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Demo Dairy Astana")
    herd_size: Mapped[int] = mapped_column(Integer, default=200)
    milk_price_kzt: Mapped[float] = mapped_column(Float, default=220.0)


class CowGroup(Base):
    __tablename__ = "cow_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    cow_count: Mapped[int] = mapped_column(Integer, default=50)
    body_weight_kg: Mapped[float] = mapped_column(Float, default=650)
    milk_yield_l: Mapped[float] = mapped_column(Float, default=30)
    target_dmi_kg: Mapped[float] = mapped_column(Float, default=22)
    min_cp_pct: Mapped[float] = mapped_column(Float, default=16.0)
    max_cp_pct: Mapped[float] = mapped_column(Float, default=19.0)
    min_ndf_pct: Mapped[float] = mapped_column(Float, default=28.0)
    max_ndf_pct: Mapped[float] = mapped_column(Float, default=36.0)
    max_starch_pct: Mapped[float] = mapped_column(Float, default=28.0)
    max_fat_pct: Mapped[float] = mapped_column(Float, default=6.0)
    min_me_mcal_per_kg_dm: Mapped[float] = mapped_column(Float, default=2.25)
    min_ca_pct: Mapped[float] = mapped_column(Float, default=0.70)
    min_p_pct: Mapped[float] = mapped_column(Float, default=0.35)
    transition_limit_pct: Mapped[float] = mapped_column(Float, default=20.0)


class Feed(Base):
    __tablename__ = "feeds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    dm_pct: Mapped[float] = mapped_column(Float)
    cp_pct: Mapped[float] = mapped_column(Float)
    ndf_pct: Mapped[float] = mapped_column(Float)
    starch_pct: Mapped[float] = mapped_column(Float, default=0)
    fat_pct: Mapped[float] = mapped_column(Float, default=0)
    me_mcal_per_kg_dm: Mapped[float] = mapped_column(Float)
    ca_pct: Mapped[float] = mapped_column(Float, default=0)
    p_pct: Mapped[float] = mapped_column(Float, default=0)
    price_kzt_per_kg: Mapped[float] = mapped_column(Float)
    min_as_fed_kg: Mapped[float] = mapped_column(Float, default=0)
    max_as_fed_kg: Mapped[float] = mapped_column(Float, default=50)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RationLine(Base):
    __tablename__ = "ration_lines"
    __table_args__ = (UniqueConstraint("group_id", "feed_id", name="uq_group_feed"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("cow_groups.id", ondelete="CASCADE"), index=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id", ondelete="CASCADE"), index=True)
    kg_as_fed: Mapped[float] = mapped_column(Float, default=0)


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("cow_groups.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    before_cost_kzt: Mapped[float] = mapped_column(Float, default=0)
    after_cost_kzt: Mapped[float] = mapped_column(Float, default=0)
    savings_per_cow_day_kzt: Mapped[float] = mapped_column(Float, default=0)
    savings_group_month_kzt: Mapped[float] = mapped_column(Float, default=0)
    before_json: Mapped[dict] = mapped_column(JSON, default=dict)
    proposed_json: Mapped[dict] = mapped_column(JSON, default=dict)
    nutrients_json: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("group_id", "observed_on", name="uq_group_observed_on"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("cow_groups.id", ondelete="CASCADE"), index=True)
    observed_on: Mapped[date] = mapped_column(Date)
    milk_yield_l: Mapped[float] = mapped_column(Float)
    fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    somatic_cells_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AIExplanation(Base):
    __tablename__ = 'ai_explanations'
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AIDailyUsage(Base):
    __tablename__ = 'ai_daily_usage'
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class OptimizationSnapshot(Base):
    """Separate additive table: legacy runs have no snapshot and cannot be applied."""
    __tablename__ = 'optimization_snapshots'
    run_id: Mapped[int] = mapped_column(ForeignKey('optimization_runs.id'), primary_key=True)
    inputs_json: Mapped[dict] = mapped_column(JSON)


class EconomicsEntry(Base):
    """Append-only daily totals; a correction inserts a new revision."""
    __tablename__ = 'economics_entries'
    __table_args__ = (UniqueConstraint('group_id', 'day', 'revision', name='uq_economics_revision'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('cow_groups.id'), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

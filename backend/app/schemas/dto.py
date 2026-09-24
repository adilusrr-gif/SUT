from datetime import date
from pydantic import BaseModel, Field, ConfigDict, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class FarmIn(InputModel):
    name: str = "Demo Dairy Astana"
    herd_size: int = Field(ge=1, le=100000)
    milk_price_kzt: float = Field(gt=0)


class GroupIn(InputModel):
    farm_id: int = 1
    name: str = Field(min_length=1, max_length=120)
    cow_count: int = Field(ge=1)
    body_weight_kg: float = Field(gt=100)
    milk_yield_l: float = Field(ge=0)
    target_dmi_kg: float = Field(gt=5)
    min_cp_pct: float = Field(default=16, ge=0, le=100)
    max_cp_pct: float = Field(default=19, ge=0, le=100)
    min_ndf_pct: float = Field(default=28, ge=0, le=100)
    max_ndf_pct: float = Field(default=36, ge=0, le=100)
    max_starch_pct: float = Field(default=28, ge=0, le=100)
    max_fat_pct: float = Field(default=6, ge=0, le=100)
    min_me_mcal_per_kg_dm: float = Field(default=2.25, gt=0)
    min_ca_pct: float = Field(default=0.7, ge=0, le=100)
    min_p_pct: float = Field(default=0.35, ge=0, le=100)
    transition_limit_pct: float = Field(default=20, ge=0, le=100)

    @model_validator(mode='after')
    def valid_ranges(self):
        if self.min_cp_pct > self.max_cp_pct or self.min_ndf_pct > self.max_ndf_pct:
            raise ValueError('Minimum nutrient constraint must not exceed maximum')
        return self


class FeedIn(InputModel):
    name: str = Field(min_length=1, max_length=120)
    dm_pct: float = Field(gt=1, le=100)
    cp_pct: float = Field(ge=0, le=100)
    ndf_pct: float = Field(ge=0, le=100)
    starch_pct: float = Field(ge=0, le=100)
    fat_pct: float = Field(ge=0, le=100)
    me_mcal_per_kg_dm: float = Field(gt=0)
    ca_pct: float = Field(ge=0, le=100)
    p_pct: float = Field(ge=0, le=100)
    price_kzt_per_kg: float = Field(ge=0)
    min_as_fed_kg: float = Field(ge=0, default=0)
    max_as_fed_kg: float = Field(gt=0, default=50)
    active: bool = True

    @model_validator(mode='after')
    def valid_bounds(self):
        if self.min_as_fed_kg > self.max_as_fed_kg:
            raise ValueError('Minimum feed amount must not exceed maximum')
        return self


class RationLineIn(InputModel):
    feed_id: int
    kg_as_fed: float = Field(ge=0)


class RationIn(InputModel):
    lines: list[RationLineIn] = Field(max_length=1000)

    @model_validator(mode='after')
    def unique_feeds(self):
        if len({line.feed_id for line in self.lines}) != len(self.lines):
            raise ValueError('Duplicate feed IDs')
        return self


class ObservationIn(InputModel):
    group_id: int
    observed_on: date
    milk_yield_l: float = Field(ge=0)
    fat_pct: float | None = Field(default=None, ge=0, le=100)
    protein_pct: float | None = Field(default=None, ge=0, le=100)
    somatic_cells_k: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)

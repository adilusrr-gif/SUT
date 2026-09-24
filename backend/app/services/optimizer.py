from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog


@dataclass
class OptFeed:
    id: int
    name: str
    dm_pct: float
    cp_pct: float
    ndf_pct: float
    starch_pct: float
    fat_pct: float
    me_mcal_per_kg_dm: float
    ca_pct: float
    p_pct: float
    price_kzt_per_kg: float
    min_as_fed_kg: float
    max_as_fed_kg: float


def _dm(feed: OptFeed) -> float:
    return feed.dm_pct / 100.0


def nutrient_totals(feeds: list[OptFeed], amounts: list[float]) -> dict:
    dm = sum(x * _dm(f) for f, x in zip(feeds, amounts))
    def weighted(attr: str) -> float:
        if dm <= 0:
            return 0.0
        total = sum(x * _dm(f) * getattr(f, attr) / 100.0 for f, x in zip(feeds, amounts))
        return total / dm * 100.0
    me_total = sum(x * _dm(f) * f.me_mcal_per_kg_dm for f, x in zip(feeds, amounts))
    return {
        "dmi_kg": round(float(dm), 3),
        "cp_pct_dm": round(float(weighted("cp_pct")), 3),
        "ndf_pct_dm": round(float(weighted("ndf_pct")), 3),
        "starch_pct_dm": round(float(weighted("starch_pct")), 3),
        "fat_pct_dm": round(float(weighted("fat_pct")), 3),
        "ca_pct_dm": round(float(weighted("ca_pct")), 3),
        "p_pct_dm": round(float(weighted("p_pct")), 3),
        "me_mcal_per_kg_dm": round(float(me_total / dm if dm else 0), 3),
    }


def optimize(group, feeds: list[OptFeed], current: dict[int, float]) -> dict:
    if not feeds:
        return {"status": "infeasible", "message": "Нет активных кормов"}

    c = np.array([f.price_kzt_per_kg for f in feeds], dtype=float)
    target = float(group.target_dmi_kg)
    dmi_low, dmi_high = target * 0.98, target * 1.02

    A_ub: list[list[float]] = []
    b_ub: list[float] = []

    dmcoef = [f.dm_pct / 100.0 for f in feeds]
    # DMI lower/upper
    A_ub.append([-v for v in dmcoef]); b_ub.append(-dmi_low)
    A_ub.append(dmcoef); b_ub.append(dmi_high)

    # Fractions are constrained against actual dry matter, not the target.
    def ratio_bound(attr, bound, lower=False, scale=100.0):
        row = [dm * (getattr(f, attr) - bound) / scale for f, dm in zip(feeds, dmcoef)]
        A_ub.append([-v for v in row] if lower else row)
        b_ub.append(0.0)

    for attr, low, high in [('cp_pct', group.min_cp_pct, group.max_cp_pct),
                            ('ndf_pct', group.min_ndf_pct, group.max_ndf_pct)]:
        ratio_bound(attr, low, lower=True)
        ratio_bound(attr, high)
    ratio_bound('starch_pct', group.max_starch_pct)
    ratio_bound('fat_pct', group.max_fat_pct)
    ratio_bound('me_mcal_per_kg_dm', group.min_me_mcal_per_kg_dm, lower=True, scale=1.0)
    ratio_bound('ca_pct', group.min_ca_pct, lower=True)
    ratio_bound('p_pct', group.min_p_pct, lower=True)

    bounds = []
    t = max(0.0, min(float(group.transition_limit_pct), 100.0)) / 100.0
    for f in feeds:
        cur = float(current.get(f.id, 0.0))
        if cur > 0:
            low = max(f.min_as_fed_kg, cur * (1 - t))
            high = min(f.max_as_fed_kg, cur * (1 + t))
        else:
            # New feeds enter gradually; 1.5 kg/cow/day max on first transition step.
            low = f.min_as_fed_kg
            high = min(f.max_as_fed_kg, 1.5)
        bounds.append((low, high))

    if any(low > high for low, high in bounds):
        return {"status": "infeasible", "message": "Границы кормов несовместимы с ограничением перехода"}
    res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub), bounds=bounds, method="highs")
    if not res.success:
        return {
            "status": "infeasible",
            "message": "Безопасный переходный шаг не найден. Проверьте ограничения, состав кормов и доступность. Не применяйте автоматические изменения.",
            "solver_message": res.message,
        }

    x = np.maximum(res.x, 0)
    proposed = {f.id: float(v) for f, v in zip(feeds, x)}
    before = {f.id: float(current.get(f.id, 0.0)) for f in feeds}
    before_cost = sum(current.get(f.id, 0.0) * f.price_kzt_per_kg for f in feeds)
    after_cost = float(res.fun)
    nutrients = nutrient_totals(feeds, list(x))

    warnings = [
        "Рацион является расчётным предложением и требует подтверждения зоотехника.",
        f"Ограничение перехода: не более {group.transition_limit_pct:.0f}% изменения существующего корма за шаг; новый корм ≤ 1.5 кг/корову/день.",
        "Фактический состав кормов желательно обновлять по лабораторному анализу; усреднённые значения могут давать существенную погрешность.",
    ]
    return {
        "status": "ok",
        "before": before,
        "proposed": proposed,
        "before_cost_kzt": round(before_cost, 2),
        "after_cost_kzt": round(after_cost, 2),
        "savings_per_cow_day_kzt": round(before_cost - after_cost, 2),
        "nutrients": nutrients,
        "warnings": warnings,
    }

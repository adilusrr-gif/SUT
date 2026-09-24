from types import SimpleNamespace
from app.services.optimizer import OptFeed, optimize


def test_demo_optimizer_is_feasible_and_cheaper():
    feeds = [
        OptFeed(1,"silage",35,8,45,28,3,2.25,.30,.22,18,12,30),
        OptFeed(2,"hay",88,18,42,2,2.5,2.05,1.35,.25,75,1,8),
        OptFeed(3,"barley",88,12,20,58,2.2,3.05,.08,.38,105,0,8),
        OptFeed(4,"soy",90,48,12,3,2,2.95,.30,.65,245,0,5),
        OptFeed(5,"rapeseed",90,38,24,5,3,2.65,.70,1.10,165,0,5),
        OptFeed(6,"mineral",95,0,0,0,0,.2,18,7,380,.15,.6),
    ]
    group = SimpleNamespace(target_dmi_kg=22,min_cp_pct=15.5,max_cp_pct=19,min_ndf_pct=28,max_ndf_pct=38,max_starch_pct=30,max_fat_pct=6,min_me_mcal_per_kg_dm=2.15,min_ca_pct=.62,min_p_pct=.32,transition_limit_pct=20)
    current = {1:24,2:5,3:5,4:2.5,5:1.2,6:.35}
    result = optimize(group, feeds, current)
    assert result["status"] == "ok"
    assert result["after_cost_kzt"] < result["before_cost_kzt"]
    assert 21.56 <= result["nutrients"]["dmi_kg"] <= 22.44
    assert result["nutrients"]["cp_pct_dm"] >= 15.5
    assert result["nutrients"]["ndf_pct_dm"] >= 28

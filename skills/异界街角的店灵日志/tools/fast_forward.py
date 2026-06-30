"""
fast_forward.py — 快速模式（蓝本五）

确定性地模拟 N 个游戏日：每日跑午前/午后营业 + 打烊结算 + SP 恢复 + 进度，
聚合为苏醒摘要。期间若 G 类主线就绪 → 立即中断（interrupted），交回日常模式。
不暂停、不生成叙事，只返回结构化结果。
"""
from __future__ import annotations
import random

import gamedata as G
import economy as E
import spirit as SP
import progression as PR


def roll_weather(season: str, rng: random.Random) -> str:
    weights = G.SEASON_WEATHER_WEIGHTS.get(season, {"晴": 1})
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _rollover(sim: dict) -> None:
    sim["day"] += 1
    sim["today_in"] = 0
    sim["today_out"] = 0
    sim["events_today"] = []
    sim["block_idx"] = 0
    sim["block"] = G.BLOCKS[0]
    E.overnight_recovery(sim)


def simulate_days(sim: dict, n: int, rng: random.Random, phase: str) -> dict:
    start = {"day": sim["day"], "prosperity": sim["prosperity"],
             "balance": round(sim["balance"], 1)}
    per_day = []
    interrupted = None

    for _ in range(max(1, n)):
        sim["weather"] = roll_weather(sim["season"], rng)
        sim["special_day"] = "集市日" if sim["day"] % 6 == 0 else ""

        SP.regen(sim)                                   # 晨备→午前
        am = E.simulate_business_block(sim, "午前营业", rng)
        SP.regen(sim)                                   # 午前→午后
        pm = E.simulate_business_block(sim, "午后营业", rng)
        SP.regen(sim)                                   # 午后→打烊
        settle = E.settle_day(sim, rng)
        SP.regen(sim)                                   # 打烊→次日
        SP.maybe_upgrade(sim)

        if sim["prosperity"] >= G.THRESHOLDS["P_ACT_3_PROSPERITY"]:
            sim["prosp_high_days"] = sim.get("prosp_high_days", 0) + 1
        else:
            sim["prosp_high_days"] = 0

        net = round(sim["today_in"] - sim["today_out"], 1)
        per_day.append({
            "day": sim["day"], "weather": f'{sim["season"]}·{sim["weather"]}',
            "customers": am["customers"] + pm["customers"], "net": net,
            "prosperity": sim["prosperity"],
            "wages_owed": settle.get("wages_owed", []),
        })

        prog = PR.check(sim, phase)
        _rollover(sim)
        if prog["g_events"]:
            interrupted = prog["g_events"][0]
            break

    low_inv = [k for k, v in sim["inventory"].items() if v <= 3]
    return {
        "interrupted": bool(interrupted),
        "interrupt_event": interrupted,
        "days_simulated": len(per_day),
        "start": start,
        "end": {"day": sim["day"], "prosperity": sim["prosperity"],
                "balance": round(sim["balance"], 1)},
        "per_day": per_day,
        "low_inventory": low_inv,
        "next_tax_day": sim.get("next_tax_day"),
    }


if __name__ == "__main__":
    import sys, json, saveio
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(13)
    sim = saveio.default_sim()
    sim["prosperity"] = 20
    out = simulate_days(sim, 5, rng, "ACT1")
    print(json.dumps({"days": out["days_simulated"], "interrupted": out["interrupted"],
                      "start": out["start"], "end": out["end"]}, ensure_ascii=False))

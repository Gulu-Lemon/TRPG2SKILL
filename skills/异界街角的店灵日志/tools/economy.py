"""
economy.py — 经济系统：营业结算 + 每日结算（蓝本 11.2）

- simulate_business_block: 一个营业时间块的客流→出餐→收入→繁荣度
- settle_day: 打烊后结算（薪资按 莉涅→巴尔德→艾达，维护，周税）
"""
from __future__ import annotations
import random

import gamedata as G
import customer_roller as CR
import quality as Q
import prosperity as P

MAINTENANCE_PER_DAY = 5  # 铜，清洁/保养小额日费


def simulate_business_block(sim: dict, block: str, rng: random.Random,
                            spirit_boost: int = 0) -> dict:
    """模拟一个营业时间块。修改 sim，返回结构化摘要。"""
    customers = CR.roll_block_customers(sim, block, rng)
    results = [Q.serve(sim, c, rng, spirit_boost=spirit_boost) for c in customers]

    sat_counts: dict[str, int] = {}
    income = tips = total_prosp = 0.0
    for r in results:
        sat_counts[r.get("sat_cn", "?")] = sat_counts.get(r.get("sat_cn", "?"), 0) + 1
        income += r.get("revenue", 0)
        tips += r.get("tip", 0)
        total_prosp += r.get("prosp_delta", 0)

    P.apply_delta(sim, int(round(total_prosp)))
    return {
        "block": block,
        "customers": len(customers),
        "served": sum(1 for r in results if r.get("served")),
        "satisfaction": sat_counts,
        "income": round(income, 1),
        "tips": round(tips, 1),
        "prosperity_delta": int(round(total_prosp)),
        "results": results,
    }


def overnight_recovery(sim: dict) -> None:
    """跨夜恢复：一夜休息后店员疲劳大幅下降、士气小幅回升（蓝本 11.5）。"""
    for npc in sim["npcs"].values():
        npc["fatigue"] = max(0, int(npc.get("fatigue", 0) * 0.4))
        if npc.get("owed_days", 0) == 0:
            npc["morale"] = min(100, npc.get("morale", 50) + 2)


def cash_status(balance: int, daily_op: int) -> str:
    if balance < 0:
        return "DEBT_CRITICAL"
    if balance < 2 * daily_op:
        return "CASH_TIGHT"
    if balance < 7 * daily_op:
        return "CASH_NORMAL"
    if balance < 14 * daily_op:
        return "CASH_COMFORTABLE"
    return "CASH_SURPLUS"


def settle_day(sim: dict, rng: random.Random) -> dict:
    """打烊后每日结算（蓝本 11.2.4）。修改 sim，返回摘要。"""
    out = {"wages_paid": {}, "wages_owed": [], "maintenance": MAINTENANCE_PER_DAY,
           "tax": 0, "tax_paid": False}

    # 维护小额
    sim["balance"] -= MAINTENANCE_PER_DAY
    sim["today_out"] = sim.get("today_out", 0) + MAINTENANCE_PER_DAY

    # 薪资：莉涅 → 巴尔德 → 艾达（艾达把自己排最后）
    for npc_id in G.WAGE_ORDER:
        npc = sim["npcs"][npc_id]
        wage = npc.get("wage", 0)
        if sim["balance"] >= wage:
            sim["balance"] -= wage
            sim["today_out"] = sim.get("today_out", 0) + wage
            npc["owed_days"] = max(0, npc.get("owed_days", 0) - 1)
            out["wages_paid"][npc["name"]] = wage
        else:
            npc["owed_days"] = npc.get("owed_days", 0) + 1
            npc["morale"] = max(0, npc.get("morale", 50) - 5)
            out["wages_owed"].append(npc["name"])

    # 周税（每 7 日，数额不定）
    if sim["day"] == sim.get("next_tax_day", 7):
        tax = rng.randint(100, 300)
        out["tax"] = tax
        if sim["balance"] >= tax:
            sim["balance"] -= tax
            sim["today_out"] = sim.get("today_out", 0) + tax
            out["tax_paid"] = True
        else:
            sim["tax_debt"] = sim.get("tax_debt", 0) + (tax - sim["balance"])
            sim["today_out"] = sim.get("today_out", 0) + sim["balance"]
            sim["balance"] = 0
        sim["next_tax_day"] = sim.get("next_tax_day", 7) + 7

    daily_op = sum(sim["npcs"][i]["wage"] for i in G.WAGE_ORDER) + MAINTENANCE_PER_DAY
    out["balance_after"] = sim["balance"]
    out["cash_status"] = cash_status(sim["balance"], daily_op)
    sim["last_settled_day"] = sim["day"]
    return out


if __name__ == "__main__":
    import sys, json, saveio
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(3)
    sim = saveio.default_sim()
    sim["prosperity"] = 30
    am = simulate_business_block(sim, "午前营业", rng)
    pm = simulate_business_block(sim, "午后营业", rng)
    sim["day"] = 7  # 触发周税
    settle = settle_day(sim, rng)
    print(json.dumps({"am_income": am["income"], "pm_income": pm["income"],
                      "prosperity": sim["prosperity"], "balance": sim["balance"],
                      "settle": settle}, ensure_ascii=False))

"""
quality.py — 出餐品质与顾客满意度（蓝本十三）

品质分 = 技能基底 + 食材加成 + 设备加成 + 店灵干预 + 随机浮动 → 四档
满意度 = 实际品质等级 - 顾客期望等级（裁剪 [-2,2]）→ 五档及后果
"""
from __future__ import annotations
import random

import gamedata as G
import menu as M

HIGH_TIERS = {"商人", "上层", "贵宾"}


def score_to_level(score: int) -> int:
    if score >= 85:
        return 3
    if score >= 65:
        return 2
    if score >= 40:
        return 1
    return 0


def compute_quality(maker: dict, skill_key: str, item: dict,
                    spirit_boost: int, rng: random.Random) -> tuple[int, int]:
    base = maker["skills"].get(skill_key, 1) * 10
    ing = 0
    for name in item["recipe"]:
        if name in M.SPECIAL_INGREDIENTS:
            ing = max(ing, 15)
        elif name in M.HIGH_INGREDIENTS:
            ing = max(ing, 10)
    equip = 5
    if maker.get("fatigue", 0) > 60:
        fluct = rng.randint(-15, 5)
    else:
        fluct = rng.randint(-10, 10)
    score = max(0, base + ing + equip + spirit_boost + fluct)
    return score, score_to_level(score)


def satisfaction(actual_level: int, expectation_level: int) -> tuple[str, str, int]:
    diff = max(-2, min(2, actual_level - expectation_level))
    return G.SATISFACTION[diff]


def _has_ingredients(sim: dict, recipe: dict) -> bool:
    inv = sim["inventory"]
    return all(inv.get(k, 0) >= qty for k, qty in recipe.items())


def _consume(sim: dict, recipe: dict) -> None:
    inv = sim["inventory"]
    for k, qty in recipe.items():
        inv[k] = inv.get(k, 0) - qty


def _pick_item(sim: dict, customer: dict, rng: random.Random) -> dict | None:
    options = [it for it in sim["menu"]
               if M.price(it, sim) <= customer["budget"] and _has_ingredients(sim, it["recipe"])]
    if not options:
        return None
    return rng.choice(options)


def _pick_maker(sim: dict, skill_key: str) -> tuple[str, dict]:
    """技能最高者优先；若其已疲惫(>60)则交给次高者，分摊负荷。"""
    ranked = sorted(sim["npcs"].items(),
                    key=lambda kv: kv[1]["skills"].get(skill_key, 0), reverse=True)
    for nid, npc in ranked:
        if npc.get("fatigue", 0) <= 60:
            return nid, npc
    return ranked[0]


def _tip(sat_code: str, revenue: float, personality: list[str],
         rng: random.Random) -> float:
    table = {"AMAZED": (0.80, 0.30), "PLEASED": (0.40, 0.15), "SATISFIED": (0.10, 0.10)}
    if sat_code not in table:
        return 0.0
    prob, rate = table[sat_code]
    if "慷慨" in personality:
        prob, rate = min(1.0, prob * 1.5), rate * 1.5
    if "吝啬" in personality:
        prob *= 0.3
    if rng.random() < prob:
        return round(revenue * rate * 2) / 2
    return 0.0


def serve(sim: dict, customer: dict, rng: random.Random,
          spirit_boost: int = 0) -> dict:
    """为一位顾客出餐结算。修改 sim（库存/收入/店员疲劳），返回结果含 prosp_delta。"""
    item = _pick_item(sim, customer, rng)
    if item is None:
        # 没有可负担/有货的品项 → 视为失望离店
        return {"served": False, "customer": customer, "reason": "no_affordable_item",
                "satisfaction": "DISAPPOINTED", "sat_cn": "失望",
                "revenue": 0, "tip": 0, "prosp_delta": -1}

    maker_id, maker = _pick_maker(sim, item["skill"])
    score, level = compute_quality(maker, item["skill"], item, spirit_boost, rng)
    sat_code, sat_cn, prosp_delta = satisfaction(level, customer["expectation"])

    revenue = M.price(item, sim)
    tip = _tip(sat_code, revenue, customer["personality"], rng)

    _consume(sim, item["recipe"])
    sim["today_in"] = sim.get("today_in", 0) + revenue + tip
    sim["balance"] = sim.get("balance", 0) + revenue + tip
    maker["fatigue"] = min(100, maker.get("fatigue", 0) + 2)

    if sat_code == "OFFENDED" and customer["tier"] in HIGH_TIERS:
        prosp_delta -= 2

    return {
        "served": True, "customer_id": customer["id"], "tier": customer["tier"],
        "item": item["name"], "maker": maker["name"],
        "quality_score": score, "quality": G.QUALITY_LEVELS[level],
        "satisfaction": sat_code, "sat_cn": sat_cn,
        "revenue": revenue, "tip": tip, "prosp_delta": prosp_delta,
    }


if __name__ == "__main__":
    import sys, json, saveio, customer_roller as CR
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(11)
    sim = saveio.default_sim()
    sim["prosperity"] = 30
    custs = CR.roll_block_customers(sim, "午后营业", rng)
    results = [serve(sim, c, rng) for c in custs]
    served = [r for r in results if r["served"]]
    print(json.dumps({
        "n": len(results), "served": len(served),
        "income": round(sim["today_in"], 1),
        "sample": served[:2],
    }, ensure_ascii=False))

"""
spirit.py — 店灵能力系统（蓝本三）

意图→能力匹配、SP/冷却/羁绊门槛/失败率/沉睡判定、SP 恢复、阶段升级。
低置信度时返回 needs_clarification（不臆测玩家意图）。
"""
from __future__ import annotations
import random

import gamedata as G
import prosperity as P

# 影响出餐品质的能力（被使用时给 quality 加成）
QUALITY_ABILITIES = {"风味暗示", "气氛微调", "暖意"}


def current_abilities(sim: dict) -> list[dict]:
    stage = sim["spirit"]["stage"]
    return [a for a in G.SPIRIT_ABILITIES if a["stage"] <= stage]


def max_bond(sim: dict) -> int:
    return max((n["bond_stars"] for n in sim["npcs"].values()), default=0)


def match_ability(text: str, sim: dict) -> dict | None:
    """根据玩家自然语言匹配最合适的可用能力；无把握返回 None。"""
    if not text:
        return None
    avail = current_abilities(sim)
    scored = []
    for ab in avail:
        hits = sum(1 for s in ab["syn"] if s in text)
        if ab["id"] in text:
            hits += 3
        if hits:
            scored.append((hits, -ab["sp"], ab))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]


def quality_boost(sim: dict) -> int:
    """店灵干预对出餐品质的加成（蓝本 13.2），按阶段取中值。"""
    return {1: 4, 2: 7, 3: 12, 4: 18}.get(sim["spirit"]["stage"], 0)


def cast(ability: dict, sim: dict, rng: random.Random) -> dict:
    sp = sim["spirit"]
    cd = sp.get("cooldowns", {}).get(ability["id"], 0)
    if cd > 0:
        return {"ok": False, "reason": f"【{ability['id']}】冷却中（剩 {cd} 时间块）。"}
    if ability["bond"] > 0 and max_bond(sim) < ability["bond"]:
        return {"ok": False,
                "reason": f"【{ability['id']}】需要与某位店员的羁绊达到 {G.bond_stars_str(ability['bond'])}。"}
    if sp["sp"] < ability["sp"]:
        return {"ok": False,
                "reason": f"灵力不足：【{ability['id']}】需 {ability['sp']} SP，当前 {sp['sp']}。"}

    sp["sp"] -= ability["sp"]
    success = (rng.random() * 100) >= sp["fail"]
    if ability["cd"] > 0:
        sp.setdefault("cooldowns", {})[ability["id"]] = ability["cd"]

    slept = 0
    if success and ability["sleep"] > 0:
        sim["mode"] = "sleep"
        sim["sleep_left"] = ability["sleep"]
        slept = ability["sleep"]

    return {
        "ok": True, "ability": ability["id"], "effect": ability["effect"],
        "success": success, "sp_cost": ability["sp"], "sp_left": sp["sp"],
        "sleep_blocks": slept,
        "note": ability["effect"] if success
        else "能力似乎没能使出来——灯火只是微微颤了一下，没人注意到。",
    }


def regen(sim: dict) -> None:
    """每推进一个时间块调用：恢复 SP、递减冷却、推进沉睡计时。"""
    sp = sim["spirit"]
    bonus = P.spirit_regen_bonus(sp["stage"], sim["prosperity"])
    sp["sp"] = min(sp["sp_max"], sp["sp"] + sp["regen"] + bonus)
    for k in list(sp.get("cooldowns", {})):
        sp["cooldowns"][k] = max(0, sp["cooldowns"][k] - 1)
        if sp["cooldowns"][k] == 0:
            del sp["cooldowns"][k]
    if sim.get("mode") == "sleep":
        sim["sleep_left"] = max(0, sim.get("sleep_left", 0) - 1)
        if sim["sleep_left"] == 0:
            sim["mode"] = "daily"


def maybe_upgrade(sim: dict) -> dict | None:
    """繁荣度跨阈值时升级店灵阶段（蓝本 3.3-3.5）。"""
    pr = sim["prosperity"]
    target = 1
    if pr >= G.THRESHOLDS["P_SPIRIT_4"]:
        target = 4
    elif pr >= G.THRESHOLDS["P_SPIRIT_3"]:
        target = 3
    elif pr >= G.THRESHOLDS["P_SPIRIT_2"]:
        target = 2
    sp = sim["spirit"]
    if target > sp["stage"]:
        old = sp["stage"]
        sp["stage"] = target
        t = G.SP_TABLE[target]
        sp["sp_max"] = t["max"]
        sp["regen"] = t["regen"]
        sp["fail"] = t["fail"]
        sp["perception"] = t["perception"]
        sp["sp"] = min(sp["sp_max"], sp["sp"])
        return {"from": old, "to": target}
    return None


if __name__ == "__main__":
    import sys, json, saveio
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(5)
    sim = saveio.default_sim()
    ab = match_ability("让艾达注意到窗台上的那封信", sim)
    res = cast(ab, sim, rng) if ab else {"matched": None}
    sim["prosperity"] = 26
    up = maybe_upgrade(sim)
    print(json.dumps({"matched": ab["id"] if ab else None, "cast": res,
                      "upgrade": up, "stage": sim["spirit"]["stage"]},
                     ensure_ascii=False))

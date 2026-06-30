"""
progression.py — 主线幕间与 G 类主线就绪判定（蓝本六 / 十五.8）

确定性地把繁荣度/羁绊/剧情状态翻译为：
- flags_to_set：供 PhaseMachine 的 has_flag 条件驱动幕间转换
- g_events：一次性主线事件就绪提示（写入 story.g_done 去重）
"""
from __future__ import annotations
import gamedata as G

ACT_BY_PHASE = {
    "PROLOGUE_PART1": "序章", "PROLOGUE_PART2": "序章", "PROLOGUE_PART3": "序章",
    "PROLOGUE_PART4": "序章", "PROLOGUE_PART5": "序章",
    "ACT1": "第一幕", "ACT2": "第二幕", "ACT3": "第三幕", "ENDING": "终局",
}

G_DEFS = [
    {"id": "g_rich_merchant", "title": "富商首访",
     "cond": lambda s: s["prosperity"] >= G.THRESHOLDS["P_RICH_MERCHANT"],
     "hint": "一位衣着考究的中年商人推门而入，他的期望是『精品』，只点一样，只有一次机会。"},
    {"id": "g_buyout", "title": "商人收购要约",
     "cond": lambda s: s["prosperity"] >= G.THRESHOLDS["P_BUYOUT"],
     "hint": "一位外地富商派人送来收购{店名}的合同——接受彻底放手、接受继续经营、或拒绝独立。"},
]


def max_bond(sim: dict) -> int:
    return max((n["bond_stars"] for n in sim["npcs"].values()), default=0)


def all_bonds_at(sim: dict, n: int) -> bool:
    return all(npc["bond_stars"] >= n for npc in sim["npcs"].values())


def check(sim: dict, phase: str) -> dict:
    """返回 {'flags': [...], 'g_events': [...]}。修改 sim.story.act / g_done。"""
    story = sim.setdefault("story", {})
    story["act"] = ACT_BY_PHASE.get(phase, story.get("act", "序章"))

    flags: list[str] = []
    pr = sim["prosperity"]

    if sim["day"] >= 2:
        flags.append("prologue_complete")
    if pr >= G.THRESHOLDS["P_ACT_1_EXIT"] and max_bond(sim) >= 3:
        flags.append("act1_exit_ready")
    if (pr >= G.THRESHOLDS["P_ACT_2_EXIT"] and sim.get("meta", {}).get("found_note")
            and "g_bardo_confess" in story.get("g_done", [])):
        flags.append("act2_exit_ready")
    if (sim.get("prosp_high_days", 0) >= 5 and all_bonds_at(sim, 5)
            and sim["spirit"]["stage"] >= 4):
        flags.append("act3_ready")

    g_events = []
    done = story.setdefault("g_done", [])
    for g in G_DEFS:
        if g["id"] not in done and g["cond"](sim):
            g_events.append({"event_id": g["id"], "category": "G",
                             "title": g["title"], "narrative_hint": g["hint"],
                             "player_hint": "这是主线时刻，玩家完全接管。"})
            done.append(g["id"])
    return {"flags": flags, "g_events": g_events}


if __name__ == "__main__":
    import sys, json, saveio
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sim = saveio.default_sim()
    sim["day"] = 3
    sim["prosperity"] = 36
    sim["npcs"]["ada"]["bond_stars"] = 3
    out = check(sim, "ACT1")
    print(json.dumps({"result": out, "act": sim["story"]["act"]}, ensure_ascii=False))

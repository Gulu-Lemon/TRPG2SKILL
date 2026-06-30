"""
saveio.py — 存档读写与初始 sim 构造（确定性工具共享）

约定（与 TRPG2SKILL 引擎契约一致）：
- 工具是"纯函数"：读 saves/autosave.json 快照 + 命令行参数 → 计算 → stdout JSON。
- 工具 **不** 直接写 autosave.json（运行期由引擎在 write_state 落盘；
  工具修改后的完整 sim 通过 stdout 的 last_tool_result 持久化，引擎 E1
  再把其中 state_patch 并入顶层 custom、flags_to_set 并入 state.flags）。

sim = 游戏全量真值，存放于 autosave.custom.last_tool_result.sim。
"""
from __future__ import annotations
import os
import json
import copy

import gamedata as G

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVES_DIR = os.path.join(_BASE, "saves")
AUTOSAVE = os.path.join(SAVES_DIR, "autosave.json")


def default_sim() -> dict:
    """构造一份全新的初始 sim（对应序章开局）。"""
    return {
        "day": 1,
        "block_idx": 0,
        "block": G.BLOCKS[0],
        "season": "秋",
        "weather": "晴",
        "special_day": "",
        "mode": "daily",          # daily / fast / sleep
        "sleep_left": 0,
        # 经济
        "balance": G.STARTING_BALANCE,
        "today_in": 0,
        "today_out": 0,
        "tax_debt": 0,
        "next_tax_day": 7,
        "last_settled_day": 0,
        # 库存 / 繁荣
        "inventory": copy.deepcopy(G.STARTING_INVENTORY),
        "prosperity": 0,
        # 店灵
        "spirit": {
            "stage": 1,
            "sp": G.SP_TABLE[1]["max"],
            "sp_max": G.SP_TABLE[1]["max"],
            "regen": G.SP_TABLE[1]["regen"],
            "fail": G.SP_TABLE[1]["fail"],
            "perception": G.SP_TABLE[1]["perception"],
            "cooldowns": {},
        },
        # NPC / 菜单 / 顾客
        "npcs": copy.deepcopy(G.INITIAL_NPCS),
        "menu": copy.deepcopy(G.INITIAL_MENU),
        "customers": {"regulars": [], "returners": [], "next_id": 1},
        # 剧情
        "story": {
            "act": "PROLOGUE",
            "g_done": [],
            "buyout": "",
            "has_body": False,
            "prosp_high_days": 0,
            "bardo_returned": False,  # 巴尔德在 PROLOGUE_PART5 才回归
        },
        "meta": {
            "found_note": False,
            "asked_annetta": False,
            "seen_bad_end_a": False,
            "seen_good_end_b": False,
        },
        "log": [],   # 最近时间块结算摘要，用于叙事/苏醒摘要
    }


_STAGE_CN = {1: "一阶", 2: "二阶", 3: "三阶", 4: "四阶"}
_MODE_CN = {"daily": "日常", "fast": "快进", "sleep": "沉睡"}


def project_patch(sim: dict, phase: str = "") -> dict:
    """把 sim 投影为 HUD 可见的顶层 custom 标量（state_patch）。

    返回的键名即面板字段名（与 loop_schema.state_fields 对应）。
    其中 'day' 为引擎顶层白名单字段，会写入 GameState.day。

    PROLOGUE_PART1 期间只返回 day，不泄漏咖啡店 HUD 字段到 LLM 上下文。
    """
    if phase.startswith("PROLOGUE_PART1"):
        return {"day": sim["day"]}
    sp = sim["spirit"]
    npc = sim["npcs"]
    weather = f'{sim["season"]}·{sim["weather"]}'
    if sim.get("special_day"):
        weather += f' · {sim["special_day"]}'
    spirit_txt = f'{_STAGE_CN.get(sp["stage"], "?")} SP{sp["sp"]}/{sp["sp_max"]}'
    mode = sim.get("mode", "daily")
    if mode == "sleep":
        spirit_txt += f' · 沉睡剩{sim.get("sleep_left", 0)}'

    def npc_line(n: dict) -> str:
        return f'疲劳{n["fatigue"]} 心情{n["morale"]} 羁绊{G.bond_stars_str(n["bond_stars"])}'

    return {
        "day": sim["day"],
        "余额": G.fmt_money(sim["balance"]),
        "繁荣度": f'{sim["prosperity"]} ({G.reputation_label(sim["prosperity"])})',
        "时间块": sim["block"],
        "天气": weather,
        "店灵": spirit_txt,
        "模式": _MODE_CN.get(mode, mode),
        "艾达": npc_line(npc["ada"]),
        "莉涅": npc_line(npc["line"]),
        "巴尔德": npc_line(npc["bardo"]),
    }


# state_fields：供前端 HUD 标注顺序（loop_schema.state_fields 引用）
STATE_FIELDS = [
    {"name": "余额", "type": "str"},
    {"name": "繁荣度", "type": "str"},
    {"name": "时间块", "type": "str"},
    {"name": "天气", "type": "str"},
    {"name": "店灵", "type": "str"},
    {"name": "模式", "type": "str"},
    {"name": "艾达", "type": "str"},
    {"name": "莉涅", "type": "str"},
    {"name": "巴尔德", "type": "str"},
]


def read_autosave() -> dict | None:
    """读取当前 autosave 快照；不存在则返回 None。"""
    if not os.path.exists(AUTOSAVE):
        return None
    try:
        with open(AUTOSAVE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_sim(state: dict | None) -> dict:
    """从 autosave 快照取出 sim；缺失字段用默认补齐。"""
    base = default_sim()
    if not state:
        return base
    ltr = (state.get("custom") or {}).get("last_tool_result") or {}
    sim = ltr.get("sim") if isinstance(ltr, dict) else None
    if not isinstance(sim, dict):
        return base
    # 浅层补齐顶层缺失键，保证向前兼容
    for k, v in base.items():
        sim.setdefault(k, v)
    return sim

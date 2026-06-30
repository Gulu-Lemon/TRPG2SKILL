"""
session_starter.py — 新游戏初始化（《异界街角的店灵日志》）

写出一份完整的 saves/autosave.json：
- 顶层 GameState 字段（turn/day/phase/...）
- custom 含 HUD 标量（project_patch）+ last_tool_result.sim（全量真值）

由引擎 init_session 调用；引擎随后会回读本文件作为初始状态。
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import saveio  # noqa: E402


def build_initial_state() -> dict:
    sim = saveio.default_sim()
    patch = saveio.project_patch(sim, "PROLOGUE_PART1")
    day = patch.pop("day", 1)
    custom = dict(patch)
    custom["last_tool_result"] = {
        "sim": sim,
        "events": [],
        "narrative_hint": "序章开始：现代世界。又是加班的一天。便利店的咖啡越来越难喝了。",
        "player_hint": "",
    }
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "turn": 1,
        "day": day,
        "phase": "PROLOGUE_PART1",
        "player_location": "现代世界",
        "player_name": "",
        "custom": custom,
        "npcs": {},
        "inventory": [],
        "active_events": [],
        "flags": [],
        "summaries": [],
        "lorebook_state": {},
        "last_input": "",
        "created_at": now,
        "updated_at": now,
        "history": [],
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(saveio.SAVES_DIR, exist_ok=True)
    state = build_initial_state()
    with open(saveio.AUTOSAVE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "autosave": saveio.AUTOSAVE,
                      "phase": state["phase"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""
上下文打包器 — 动态信息作为 user message 注入，保持 system prompt 静态缓存命中
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import GameState, LorebookEntry


def pack_context(state: "GameState", active_entries: list["LorebookEntry"] = None,
                 recent_history_rounds: int = 20,
                 phase_scripts: dict = None) -> str:
    """将动态上下文打包为 user role 消息内容。"""

    parts = []

    # 阶段脚本（最高优先级，原文逐字）
    scripts = (phase_scripts or {}).get(state.phase, [])
    if scripts:
        parts.append(f"【当前阶段: {state.phase} — 原文指令（逐字引用，必须遵守）】")
        for s in scripts:
            parts.append(f"> {s}")

    # 状态快照
    parts.append(f"【当前状态】轮次:{state.turn} 天数:{state.day} 阶段:{state.phase} 位置:{state.player_location}")

    if state.active_events:
        events = ", ".join(
            e.get("event", str(e))[:40] for e in state.active_events[:5]
        )
        parts.append(f"活跃事件: {events}")
    if state.inventory:
        parts.append(f"持有: {', '.join(state.inventory[:10])}")
    if state.flags:
        parts.append(f"标记: {', '.join(state.flags[-10:])}")
    for key, val in state.custom.items():
        if isinstance(val, (int, float, str, bool)):
            parts.append(f"{key}: {val}")

    # 近年历史
    if state.history:
        parts.append("\n【最近剧情】")
        recent = state.history[-recent_history_rounds:]
        for r in recent:
            parts.append(f"--- 轮{r.turn} ---")
            if r.player_input:
                parts.append(f"玩家: {r.player_input}")
            if r.narrative:
                parts.append(f"GM: {r.narrative}")

    # Lorbebook
    if active_entries:
        after_agents = [e for e in active_entries if e.position.value == "after_agents"]
        after_instr = [e for e in active_entries if e.position.value == "after_instr"]
        lorebook_parts = after_agents + after_instr
        if lorebook_parts:
            parts.append("\n【背景知识】")
            for e in lorebook_parts:
                parts.append(f"## {e.title}\n{e.content}")

    return "\n\n".join(parts)

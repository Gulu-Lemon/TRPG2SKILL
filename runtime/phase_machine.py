"""
阶段状态机 — 管理游戏阶段转换
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from core.state import PhaseSpec

if TYPE_CHECKING:
    from core.state import GameState


class PhaseMachine:
    """从 loop_schema.json 的 phases 定义驱动"""

    def __init__(self, phases: list[PhaseSpec]):
        self.phases = {p.name: p for p in phases}
        self.current: str = phases[0].name if phases else "MAIN"

    def tick(self, state: GameState, turns_in_phase: int = 0) -> bool:
        """检查是否应推进阶段。返回 True 表示发生了转换。"""
        phase = self.phases.get(self.current)
        if not phase or not phase.next_phase:
            return False

        if self._evaluate(phase.condition, state):
            old = self.current
            self.current = phase.next_phase
            state.add_log(f"[阶段转换] {old} → {self.current}")
            return True
        return False

    def _evaluate(self, condition: str, state: GameState) -> bool:
        """评估阶段转换条件表达式"""
        if not condition:
            return False

        try:
            # 支持的简单表达式:
            # "prologue_complete" → state.has_flag("prologue_complete")
            # "day >= 3" → state.day >= 3
            # "turn > 10" → state.turn > 10
            
            if ">=" in condition:
                field, val = condition.split(">=")
                return getattr(state, field.strip(), 0) >= int(val.strip())
            elif "<=" in condition:
                field, val = condition.split("<=")
                return getattr(state, field.strip(), 0) <= int(val.strip())
            elif ">" in condition:
                field, val = condition.split(">")
                return getattr(state, field.strip(), 0) > int(val.strip())
            elif "<" in condition:
                field, val = condition.split("<")
                return getattr(state, field.strip(), 0) < int(val.strip())
            elif "==" in condition:
                field, val = condition.split("==")
                actual = getattr(state, field.strip(), None)
                return str(actual) == val.strip().strip("'\"")
            else:
                # 默认: 作为 flag 检查
                return state.has_flag(condition.strip())
        except Exception:
            return False

    def set_phase(self, name: str):
        """手动设置阶段"""
        if name in self.phases:
            self.current = name

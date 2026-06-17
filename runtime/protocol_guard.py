"""
协议检查官 — 防 LLM 规则漂移
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import GameState
    from core.llm import LLMClient


class ProtocolGuard:
    """每 N 轮用 LLM 自审最近的叙事输出是否违反 AGENTS.md 禁令"""

    def __init__(self, agents_md: str, config: dict, llm: LLMClient):
        self.agents_md = agents_md
        self.config = config
        self.llm = llm
        self.last_check_turn = 0

    @property
    def enabled(self) -> bool:
        return self.config.get("protocol_guard", {}).get("enabled", True)

    @property
    def interval(self) -> int:
        return self.config.get("protocol_guard", {}).get("check_interval_rounds", 5)

    @property
    def review_window(self) -> int:
        return self.config.get("protocol_guard", {}).get("review_window_rounds", 5)

    def should_check(self, state: GameState) -> bool:
        return self.enabled and (state.turn - self.last_check_turn) >= self.interval

    def check(self, state: GameState) -> str:
        """执行协议检查，返回检查结果文本"""
        recent = state.get_recent_turns(self.review_window)
        if not recent.strip():
            return "OK"

        prompt = f"""{self.agents_md}

你是协议检查官。检查上述最近 {self.review_window} 轮的叙事输出。

逐条对照以上绝对禁令检查:
1. 有任何一条输出违反了禁令吗？
2. 叙事风格偏离了核心要求吗？

如果发现违规，指出具体哪条禁令被违反，并给出纠正后的叙事。
如果无违规，只输出 "OK"。
"""
        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": recent}],
                system=prompt,
                temperature=0.3,
            )
        except Exception:
            return "OK"

        self.last_check_turn = state.turn

        if "OK" not in result:
            state.add_log(f"[协议检查] {result[:200]}")
            return result
        return "OK"

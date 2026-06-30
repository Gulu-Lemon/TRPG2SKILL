"""
对话记忆管理器 — 全量历史输出（128K+ 窗口无需裁剪）
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import GameState
    from core.llm import LLMClient
    from runtime.lorebook import LorebookManager


class MemoryManager:
    """管理对话历史。128K+ 窗口版本：不做裁剪，全量输出。"""

    def __init__(self, config: dict = None, lorebook: LorebookManager = None):
        self.config = config or {}
        self.lorebook = lorebook
        self.summary_counter = 0

    @property
    def summary_interval(self) -> int:
        return self.config.get("memory", {}).get("summary_interval_rounds", 30)

    @property
    def max_summaries(self) -> int:
        return self.config.get("memory", {}).get("max_summary_entries", 5)

    def build_messages(self, state: GameState) -> list[dict]:
        """全量返回历史消息。"""
        messages = []

        if state.summaries:
            block = "【此前剧情摘要】\n" + "\n".join(
                f"- {s}" for s in state.summaries[-self.max_summaries:]
            )
            messages.append({"role": "user", "content": block})

        for record in state.history:
            if record.player_input:
                messages.append({"role": "user", "content": record.player_input})
            if record.narrative:
                messages.append({"role": "assistant", "content": record.narrative})

        return messages

    def maybe_generate_summary(self, state: GameState, llm: LLMClient):
        if state.turn % self.summary_interval != 0 or state.turn < self.summary_interval:
            return

        start_turn = max(1, state.turn - self.summary_interval)
        recent = [r for r in state.history if start_turn <= r.turn <= state.turn]
        if len(recent) < 3:
            return

        recent_text = "\n".join(
            f"[轮{r.turn}] 玩家:{r.player_input[:80]} GM:{r.narrative[:120]}"
            for r in recent
        )

        try:
            summary = llm.chat(
                messages=[{"role": "user", "content": recent_text}],
                system="将以上剧情总结为一段话（≤300字）。突出关键事件和角色变化。",
                temperature=0.5,
            )
        except Exception:
            return

        state.summaries.append(summary)
        if len(state.summaries) > self.max_summaries:
            state.summaries = state.summaries[-self.max_summaries:]

        if self.lorebook:
            self.summary_counter += 1
            try:
                keys = llm.chat(
                    messages=[{"role": "user", "content": summary}],
                    system="提取3-5个关键词（逗号分隔）。只输出关键词。",
                    temperature=0.3,
                ).strip().split(",")
                keys = [k.strip() for k in keys if len(k.strip()) >= 2]
            except Exception:
                keys = [f"摘要{self.summary_counter}"]

            turn_range = f"第{start_turn}-{state.turn}轮"
            self.lorebook.generate_summary_entry(summary, keys, turn_range)

    def force_summary(self, state: GameState, llm: LLMClient):
        old = self.config.get("memory", {}).get("summary_interval_rounds", 30)
        self.config.setdefault("memory", {})["summary_interval_rounds"] = 1
        try:
            self.maybe_generate_summary(state, llm)
        finally:
            self.config["memory"]["summary_interval_rounds"] = old

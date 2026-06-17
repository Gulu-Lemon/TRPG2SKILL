"""
System Prompt 组装器 — 只产出静态 system prompt（实现 DeepSeek 缓存命中）
所有动态信息通过 context_packer 以 user role 注入。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from runtime.lorebook import LorebookManager


class PromptAssembler:
    """组装静态 System Prompt。每游戏唯一，跨轮次不变。"""

    def __init__(self, agents_md: str, lorebook: "LorebookManager" = None,
                 game_name: str = ""):
        self.agents_md = agents_md.strip()
        self.lorebook = lorebook
        self.game_name = game_name
        self._static_prompt = self._build_static()

    def _build_static(self) -> str:
        parts = [self.agents_md]

        bits = []
        if self.game_name:
            bits.append(f"游戏: {self.game_name}")
        if bits:
            parts.append(" | ".join(bits))

        return "\n\n".join(parts)

    @property
    def system_prompt(self) -> str:
        return self._static_prompt

    def build(self) -> str:
        return self._static_prompt

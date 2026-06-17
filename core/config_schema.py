"""
配置 Schema — 所有可调参数的元信息 + ConfigManager

每个配置项包含: key, type, default, min_val, max_val, description
GUI 可直接读取 description 作为 tooltip。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
import json
import os


@dataclass
class ConfigField:
    key: str
    type: type
    default: Any
    min_val: Any = None
    max_val: Any = None
    description: str = ""
    category: str = ""


# ═══════════════════════════════════════════════════════════
# 所有可调参数
# ═══════════════════════════════════════════════════════════

CONFIG_SCHEMA: dict[str, ConfigField] = {
    # ── Lorebook ──
    "lorebook.max_injection_tokens": ConfigField(
        key="lorebook.max_injection_tokens",
        type=int, default=3000, min_val=500, max_val=8000,
        description="单次注入 System Prompt 的 Lorebook 条目总量上限",
        category="lorebook",
    ),
    "lorebook.default_scan_depth": ConfigField(
        key="lorebook.default_scan_depth",
        type=int, default=5, min_val=1, max_val=20,
        description="扫描最近多少条消息查找触发关键词",
        category="lorebook",
    ),
    "lorebook.recursive_depth": ConfigField(
        key="lorebook.recursive_depth",
        type=int, default=1, min_val=0, max_val=3,
        description="递归触发深度（已激活条目内容触发更多条目）",
        category="lorebook",
    ),
    "lorebook.single_char_penalty": ConfigField(
        key="lorebook.single_char_penalty",
        type=float, default=0.3, min_val=0.0, max_val=1.0,
        description="单字关键词命中的权重衰减系数",
        category="lorebook",
    ),

    # ── 对话记忆 ──
    "memory.recent_window_rounds": ConfigField(
        key="memory.recent_window_rounds",
        type=int, default=15, min_val=3, max_val=50,
        description="完整保留最近 N 轮对话",
        category="memory",
    ),
    "memory.summary_interval_rounds": ConfigField(
        key="memory.summary_interval_rounds",
        type=int, default=30, min_val=10, max_val=100,
        description="每 N 轮自动生成一次剧情摘要",
        category="memory",
    ),
    "memory.max_summary_entries": ConfigField(
        key="memory.max_summary_entries",
        type=int, default=5, min_val=1, max_val=20,
        description="最多保留多少个摘要条目在内存中",
        category="memory",
    ),

    # ── 叙事生成 ──
    "narrative.temperature": ConfigField(
        key="narrative.temperature",
        type=float, default=0.9, min_val=0.1, max_val=2.0,
        description="叙事生成的随机程度。低=稳定，高=创意",
        category="narrative",
    ),
    "narrative.max_tokens": ConfigField(
        key="narrative.max_tokens",
        type=int, default=0, min_val=0, max_val=32000,
        description="叙事最大输出长度（0=不限制）",
        category="narrative",
    ),

    # ── 协议检查 ──
    "protocol_guard.enabled": ConfigField(
        key="protocol_guard.enabled",
        type=bool, default=True,
        description="是否启用定期规则偏离检查",
        category="protocol_guard",
    ),
    "protocol_guard.check_interval_rounds": ConfigField(
        key="protocol_guard.check_interval_rounds",
        type=int, default=5, min_val=1, max_val=20,
        description="每 N 轮检查一次规则偏离",
        category="protocol_guard",
    ),
    "protocol_guard.review_window_rounds": ConfigField(
        key="protocol_guard.review_window_rounds",
        type=int, default=5, min_val=1, max_val=10,
        description="检查时审查最近 N 轮的输出",
        category="protocol_guard",
    ),

    # ── 调试 ──
    "debug.show_token_usage": ConfigField(
        key="debug.show_token_usage",
        type=bool, default=False,
        description="每轮显示 Token 用量",
        category="debug",
    ),
    "debug.show_lorebook_hits": ConfigField(
        key="debug.show_lorebook_hits",
        type=bool, default=False,
        description="每轮显示 Lorebook 命中情况",
        category="debug",
    ),
}


# ═══════════════════════════════════════════════════════════
# ConfigManager
# ═══════════════════════════════════════════════════════════

class ConfigManager:
    """运行时配置管理器。读/写 game_config.json，支持热重载。"""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = self._defaults()
                self._save()
        else:
            self.data = self._defaults()
            self._save()

    def _defaults(self) -> dict:
        result: dict = {}
        for key, field in CONFIG_SCHEMA.items():
            parts = key.split(".")
            d = result
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            d[parts[-1]] = field.default
        return result

    def get(self, key: str) -> Any:
        """读单个配置值"""
        parts = key.split(".")
        d = self.data
        for part in parts:
            d = d.get(part, {}) if isinstance(d, dict) else {}
        return d if not isinstance(d, dict) else None

    def update(self, key: str, value: Any) -> bool:
        """验证 + 写入单个配置项。"""
        field = CONFIG_SCHEMA.get(key)
        if not field:
            raise ValueError(f"未知配置项: {key}")

        if not isinstance(value, field.type):
            if field.type == bool:
                value = str(value).lower() in ("true", "1", "yes")
            else:
                value = field.type(value)

        if field.min_val is not None and value < field.min_val:
            value = field.min_val
        if field.max_val is not None and value > field.max_val:
            value = field.max_val

        parts = key.split(".")
        d = self.data
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value

        self._save()
        return True

    def reset_all(self):
        self.data = self._defaults()
        self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def reload(self):
        self._load()

    def get_all_for_gui(self) -> list[dict]:
        """返回 GUI 可用的全部配置项元信息 + 当前值"""
        result = []
        for key, field in CONFIG_SCHEMA.items():
            current = self.get(key)
            result.append({
                "key": key,
                "type": field.type.__name__,
                "default": field.default,
                "current": current if current is not None else field.default,
                "min": field.min_val,
                "max": field.max_val,
                "description": field.description,
                "category": field.category,
            })
        return result

    def format_all(self) -> str:
        """CLI 显示用：格式化的所有配置"""
        lines = []
        for key, field in CONFIG_SCHEMA.items():
            current = self.get(key)
            val = current if current is not None else field.default
            lines.append(f"  {key} = {val}  ({field.description})")
        return "\n".join(lines)

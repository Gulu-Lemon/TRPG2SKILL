"""
Lorebook 管理器 — 关键词触发的背景知识注入系统

职责:
- 加载/保存 lorebook.json
- 每轮 resolve() 决定激活哪些条目
- 运行时动态追加条目（摘要/事件）
- 热重载支持
"""
from __future__ import annotations
from pathlib import Path
import json
from typing import Optional, TYPE_CHECKING

from core.state import LorebookEntry, LorebookStrategy, InsertPosition
from runtime.lorebook_index import LorebookIndex

if TYPE_CHECKING:
    from core.state import GameState
    from core.llm import LLMClient


class LorebookManager:
    """Lorebook 的主管理类"""

    def __init__(self, lorebook_path: Path, config: dict = None):
        self.path = lorebook_path
        self.config = config or {}
        self.entries: dict[str, LorebookEntry] = {}
        self.index = LorebookIndex([])
        self.dynamic_entries: dict[str, LorebookEntry] = {}
        self.load()

    def load(self):
        """从 disk 加载"""
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                raw_entries = data.get("entries", [])
                self.entries = {
                    e["id"]: LorebookEntry.from_dict(e) for e in raw_entries
                }
            except (json.JSONDecodeError, KeyError):
                self.entries = {}
        else:
            self.entries = {}

        all_entries = list(self.entries.values()) + list(self.dynamic_entries.values())
        self.index.build(all_entries)

    def save(self):
        """保存到 disk（仅静态条目，动态条目存到 lorebook_state）"""
        data = {
            "entries": [e.to_dict() for e in self.entries.values()],
            "generated_at": "",  # 由编译器写入
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ═══════════════════════════════════════════════
    # 核心: 每轮 resolve
    # ═══════════════════════════════════════════════

    def resolve(self, messages: list[dict], state: GameState,
                max_tokens: int = 999999) -> list[LorebookEntry]:
        """
        根据当前对话历史解析应激活的条目。
        
        Returns:
            排序后的激活条目列表（已按优先级+策略排序，已按 max_tokens 裁剪）
        """
        activated: list[LorebookEntry] = []
        seen_ids: set[str] = set()

        # Pass 1: Constant 条目 — 始终有效
        for entry in self.entries.values():
            if entry.strategy == LorebookStrategy.CONSTANT:
                activated.append(entry)
                seen_ids.add(entry.id)
        for entry in self.dynamic_entries.values():
            if entry.strategy == LorebookStrategy.CONSTANT:
                activated.append(entry)
                seen_ids.add(entry.id)

        # Pass 2: Normal 条目 — 扫描最近消息
        scan_depth = self.config.get("lorebook", {}).get("default_scan_depth", 5)
        recent_text = " ".join(
            m.get("content", "") for m in messages[-(scan_depth * 2):]
        )
        hits = self.index.scan(recent_text)

        for eid, count in hits.items():
            if count <= 0 or eid in seen_ids:
                continue
            entry = self.entries.get(eid) or self.dynamic_entries.get(eid)
            if entry and entry.strategy == LorebookStrategy.NORMAL:
                activated.append(entry)
                seen_ids.add(eid)

        # Pass 3: Selective 条目 — 全量历史扫描（每 5 轮）
        if state.turn % 5 == 0:
            full_text = " ".join(
                m.get("content", "") for m in messages
            )
            full_hits = self.index.scan(full_text)
            for eid, count in full_hits.items():
                if count <= 0 or eid in seen_ids:
                    continue
                entry = self.entries.get(eid) or self.dynamic_entries.get(eid)
                if entry and entry.strategy == LorebookStrategy.SELECTIVE:
                    activated.append(entry)
                    seen_ids.add(eid)

        # Pass 4: 递归触发
        recursive_depth = self.config.get("lorebook", {}).get("recursive_depth", 1)
        if recursive_depth > 0:
            activated = self._resolve_recursive(activated, seen_ids, depth=recursive_depth)

        # Pass 5: 排序 + 裁剪
        return self._order_and_trim(activated, max_tokens)

    def _resolve_recursive(self, activated, seen_ids, depth=1):
        """递归触发：激活条目的内容包含其他条目的关键词 → 连带激活"""
        if depth <= 0:
            return activated

        for entry in activated:
            if not entry.recursive:
                continue
            text = entry.title + " " + entry.content
            sub_hits = self.index.scan(text)
            for eid in sub_hits:
                if eid not in seen_ids:
                    new_entry = self.entries.get(eid) or self.dynamic_entries.get(eid)
                    if new_entry:
                        activated.append(new_entry)
                        seen_ids.add(eid)

        return activated

    def _order_and_trim(self, entries: list[LorebookEntry],
                        max_tokens: int) -> list[LorebookEntry]:
        """排序（priority desc, strategy order） + token 裁剪"""
        strategy_order = {
            LorebookStrategy.CONSTANT: 0,
            LorebookStrategy.NORMAL: 1,
            LorebookStrategy.SELECTIVE: 2,
        }

        # 去重
        seen = set()
        unique = []
        for e in entries:
            if e.id not in seen:
                seen.add(e.id)
                unique.append(e)

        unique.sort(key=lambda e: (-e.priority, strategy_order.get(e.strategy, 99)))

        # Token 裁剪
        result = []
        used = 0
        for entry in unique:
            tokens = len(entry.content) // 2
            if used + tokens > max_tokens and entry.strategy != LorebookStrategy.CONSTANT:
                continue
            result.append(entry)
            used += tokens

        return result

    # ═══════════════════════════════════════════════
    # 动态条目管理
    # ═══════════════════════════════════════════════

    def add_entry(self, entry: LorebookEntry):
        """动态添加条目（运行时生成）"""
        entry.is_dynamic = True
        self.dynamic_entries[entry.id] = entry
        self.index.add_entry(entry)

    def remove_entry(self, entry_id: str):
        """移除动态条目"""
        if entry_id in self.dynamic_entries:
            del self.dynamic_entries[entry_id]
            self.index.rebuild(
                list(self.entries.values()) + list(self.dynamic_entries.values())
            )

    def get_state(self) -> dict:
        """获取动态条目状态（用于持久化到 lorebook_state）"""
        return {
            eid: e.to_dict()
            for eid, e in self.dynamic_entries.items()
        }

    def restore_state(self, state: dict):
        """恢复动态条目（从存档）"""
        for eid, data in state.items():
            self.dynamic_entries[eid] = LorebookEntry.from_dict(data)
        self.index.rebuild(
            list(self.entries.values()) + list(self.dynamic_entries.values())
        )

    def generate_summary_entry(self, summary_text: str, trigger_keys: list[str],
                               turn_range: str, llm: Optional[LLMClient] = None):
        """生成并注册摘要条目"""
        entry = LorebookEntry(
            id=f"summary_{len(self.dynamic_entries):03d}",
            title=f"剧情摘要 ({turn_range})",
            content=summary_text,
            type="summary",
            keys=trigger_keys,
            strategy=LorebookStrategy.SELECTIVE,
            position=InsertPosition.AFTER_STATE,
            scan_depth=0,
            priority=3,
            recursive=False,
            is_dynamic=True,
        )
        self.add_entry(entry)
        return entry

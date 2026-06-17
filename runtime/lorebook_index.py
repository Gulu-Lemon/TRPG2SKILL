"""
Lorebook 关键词索引 — Aho-Corasick 自动机实现

支持:
- 多关键词 → 多条目映射
- O(n+m) 文本扫描（n=文本长度，m=命中数）
- 歧义消解（单字惩罚 + 共现增强）
- 热重建索引
"""
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import LorebookEntry


class LorebookIndex:
    """
    关键词 ↔ 条目双索引。
    
    forward:  key → set of entry_ids
    reverse:  entry_id → set of keys
    automaton: Aho-Corasick 自动机，一次扫描完成全部匹配
    """

    def __init__(self, entries: list[LorebookEntry]):
        self.entries: dict[str, LorebookEntry] = {}
        self.forward: dict[str, set[str]] = defaultdict(set)
        self.reverse: dict[str, set[str]] = defaultdict(set)
        self.automaton = None
        self._built = False
        if entries:
            self.build(entries)

    def build(self, entries: list[LorebookEntry]):
        """构建索引和 Aho-Corasick 自动机"""
        self.entries = {e.id: e for e in entries}
        self.forward.clear()
        self.reverse.clear()

        try:
            import ahocorasick
            use_ahocorasick = True
        except ImportError:
            use_ahocorasick = False

        if use_ahocorasick:
            self._build_ahocorasick()
        else:
            self._build_fallback()

        self._built = True

    def _build_ahocorasick(self):
        import ahocorasick
        self.automaton = ahocorasick.Automaton()

        for entry in self.entries.values():
            if entry.strategy.value == "constant":
                continue
            for key in entry.keys:
                key_lower = key.lower().strip()
                if len(key_lower) < 2:
                    continue

                if key_lower in self.automaton:
                    existing = self.automaton.get(key_lower, set())
                    existing.add(entry.id)
                    self.automaton.add_word(key_lower, existing)
                else:
                    self.automaton.add_word(key_lower, {entry.id})

                self.forward[key_lower].add(entry.id)
                self.reverse[entry.id].add(key_lower)

        self.automaton.make_automaton()

    def _build_fallback(self):
        """无 pyahocorasick 时的纯 Python 回退"""
        self._keyword_list: list[tuple[str, str]] = []
        for entry in self.entries.values():
            if entry.strategy.value == "constant":
                continue
            for key in entry.keys:
                key_lower = key.lower().strip()
                if len(key_lower) < 2:
                    continue
                self._keyword_list.append((key_lower, entry.id))
                self.forward[key_lower].add(entry.id)
                self.reverse[entry.id].add(key_lower)

    def scan(self, text: str) -> dict[str, int]:
        """
        扫描文本，返回 {entry_id: hit_count}。
        单字 key 自动惩罚。
        """
        if not self._built:
            return {}

        text_lower = text.lower()
        raw_hits: dict[str, int] = defaultdict(int)

        if self.automaton is not None:
            for end_idx, entry_ids in self.automaton.iter(text_lower):
                for eid in entry_ids:
                    raw_hits[eid] += 1
        else:
            for key_lower, eid in self._keyword_list:
                count = text_lower.count(key_lower)
                if count > 0:
                    raw_hits[eid] += count

        return self._resolve_ambiguity(raw_hits)

    def _resolve_ambiguity(self, raw_hits: dict[str, int], 
                           single_char_penalty: float = 0.3) -> dict[str, int]:
        """
        歧义消解:
        - L1: Aho-Corasick 最长匹配优先（内建）
        - L2: 单字 key 命中衰减
        - L3: 多字 key 共现增强
        """
        resolved: dict[str, int] = {}
        for eid, count in raw_hits.items():
            if eid not in self.entries:
                continue
            score = float(count)

            # L2: 单字惩罚
            keys = self.reverse.get(eid, set())
            single_char_count = sum(1 for k in keys if len(k) < 2)
            if single_char_count > 0 and count == single_char_count:
                score *= single_char_penalty

            # L3: 共现增强（如果有两个以上多字 key 同时命中）
            multi_char_hits = sum(
                1 for k in keys if len(k) >= 2 and k in str(raw_hits).lower()
            )
            if multi_char_hits >= 2:
                score *= 1.5

            resolved[eid] = int(score) if score == int(score) else score

        return resolved

    def rebuild(self, entries: list[LorebookEntry]):
        """热重载：全文重建索引"""
        self.build(entries)

    def add_entry(self, entry: LorebookEntry):
        """增量添加条目并更新索引（用于运行时动态条目）"""
        self.entries[entry.id] = entry
        if entry.strategy.value == "constant":
            return

        for key in entry.keys:
            key_lower = key.lower().strip()
            if len(key_lower) < 2:
                continue
            self.forward[key_lower].add(entry.id)
            self.reverse[entry.id].add(key_lower)

            if self.automaton is not None:
                if key_lower in self.automaton:
                    existing = self.automaton.get(key_lower, set())
                    existing.add(entry.id)
                    self.automaton.add_word(key_lower, existing)
                else:
                    self.automaton.add_word(key_lower, {entry.id})
                self.automaton.make_automaton()

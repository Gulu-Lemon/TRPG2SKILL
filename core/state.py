"""
核心数据结构 — 编译器分析输出、SKILL规格、运行时游戏状态、Lorebook条目

所有 dataclass 必须在编译器和运行时之间保持一致。
修改字段时检查 to_dict / from_dict 序列化。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import json
import time


# ═══════════════════════════════════════════════════════════
# Lorebook
# ═══════════════════════════════════════════════════════════

class LorebookStrategy(str, Enum):
    CONSTANT = "constant"    # 始终注入
    NORMAL = "normal"        # 最近 N 条消息命中关键词时注入
    SELECTIVE = "selective"  # 全历史命中时注入（低频检查）


class InsertPosition(str, Enum):
    AFTER_AGENTS = "after_agents"         # AGENTS.md 之后，步骤指令之前
    AFTER_INSTRUCTION = "after_instr"     # 步骤指令之后，状态快照之前
    AFTER_STATE = "after_state"           # 状态快照之后（低优先级）


@dataclass
class LorebookEntry:
    """Lorebook 中的单条记忆条目"""
    id: str
    title: str
    content: str
    type: str = "npc"                     # npc / location / item / rule / event / summary
    keys: list[str] = field(default_factory=list)
    strategy: LorebookStrategy = LorebookStrategy.NORMAL
    position: InsertPosition = InsertPosition.AFTER_INSTRUCTION
    scan_depth: int = 5
    priority: int = 10
    recursive: bool = False
    is_dynamic: bool = False              # 运行时生成（摘要等）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "type": self.type,
            "keys": self.keys,
            "strategy": self.strategy.value,
            "position": self.position.value,
            "scan_depth": self.scan_depth,
            "priority": self.priority,
            "recursive": self.recursive,
            "is_dynamic": self.is_dynamic,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LorebookEntry":
        return cls(
            id=d["id"],
            title=d["title"],
            content=d["content"],
            type=d.get("type", "npc"),
            keys=d.get("keys", []),
            strategy=LorebookStrategy(d.get("strategy", "normal")),
            position=InsertPosition(d.get("position", "after_instr")),
            scan_depth=d.get("scan_depth", 5),
            priority=d.get("priority", 10),
            recursive=d.get("recursive", False),
            is_dynamic=d.get("is_dynamic", False),
        )


# ═══════════════════════════════════════════════════════════
# 编译器阶段
# ═══════════════════════════════════════════════════════════

@dataclass
class EntitySet:
    """编译器从世界书中提取的所有实体"""
    world_summary: str = ""
    npcs: list[dict] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    factions: list[dict] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)  # [{title, text}]


@dataclass
class MechanicsDef:
    """游戏机制定义"""
    dice_system: str = ""                # "d20" / "d6" / "none"
    skill_checks: list[str] = field(default_factory=list)
    status_effects: list[str] = field(default_factory=list)
    affection_system: bool = False
    inventory_system: bool = False
    time_system: str = ""                # "day_night" / "time_blocks" / "none"


@dataclass
class NarrativeStructure:
    """叙事结构定义"""
    has_prologue: bool = False
    prologue_scenes: int = 0
    phases: list[dict] = field(default_factory=list)  # [{name, next, condition}]
    phase_scripts: dict[str, list[str]] = field(default_factory=dict)  # {"PROLOGUE": ["指令1", ...]}
    day_night_cycle: bool = False
    time_block_system: str = ""
    player_style: str = "player_driven"  # player_driven / story_driven / mixed


@dataclass
class RulesDef:
    """规则定义"""
    absolute_bans: list[dict] = field(default_factory=list)  # [{title, text}]
    phase_constraints: dict[str, list[str]] = field(default_factory=dict)
    background_knowledge: list[str] = field(default_factory=list)


@dataclass
class RandomnessNeeds:
    """随机性需求"""
    need_npc_roller: bool = False
    need_event_roller: bool = False
    need_location_roller: bool = False
    need_item_roller: bool = False
    npc_pool: list[str] = field(default_factory=list)
    event_pool: list[str] = field(default_factory=list)
    location_pool: list[str] = field(default_factory=list)
    item_pool: list[str] = field(default_factory=list)


@dataclass
class SchemaAnalysis:
    """编译器分析阶段输出"""
    game_name: str = ""
    genre: str = ""
    tone: str = ""
    player_style: str = "player_driven"
    entities: EntitySet = field(default_factory=EntitySet)
    mechanics: MechanicsDef = field(default_factory=MechanicsDef)
    narrative: NarrativeStructure = field(default_factory=NarrativeStructure)
    rules: RulesDef = field(default_factory=RulesDef)
    randomness: RandomnessNeeds = field(default_factory=RandomnessNeeds)
    state_fields: list[dict] = field(default_factory=list)  # [{name, type, default}]
    tool_specs: list[dict] = field(default_factory=list)  # [{filename, description, data_pool}]


# ═══════════════════════════════════════════════════════════
# SKILL 规格
# ═══════════════════════════════════════════════════════════

@dataclass
class PhaseSpec:
    name: str
    next_phase: Optional[str] = None
    condition: str = ""                  # "prologue_complete" / "day >= 3"
    loop_variant: str = "default"        # 不同阶段可能用不同循环

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "next": self.next_phase,
            "condition": self.condition,
            "loop_variant": self.loop_variant,
        }


@dataclass
class LoopStep:
    step: int
    type: str  # read_state / route / tool / llm_narrative / pause / llm_process / write_state
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"step": self.step, "type": self.type, **self.params}


@dataclass
class FrontmatterSpec:
    name: str
    trigger_word: str
    description: str = ""
    version: str = "1.1.0"


@dataclass
class SkillSpec:
    """经过映射后的完整 SKILL 规格"""
    frontmatter: FrontmatterSpec = field(default_factory=lambda: FrontmatterSpec("", ""))
    phases: list[PhaseSpec] = field(default_factory=list)
    loop: list[LoopStep] = field(default_factory=list)
    agents_md_rules: list[dict] = field(default_factory=list)
    lorebook_entries: list[LorebookEntry] = field(default_factory=list)
    reference_files: list[dict] = field(default_factory=list)  # [{filename, title, content}]
    tools: list[dict] = field(default_factory=list)            # [{filename, type, data_pools}]
    state_fields: list[dict] = field(default_factory=list)
    prompts: dict[str, str] = field(default_factory=dict)      # {prompt_key: template_text}
    phase_scripts: dict[str, list[str]] = field(default_factory=dict)
    generated_at: str = ""

    def to_json(self) -> dict:
        return {
            "game_name": self.frontmatter.name,
            "trigger_word": self.frontmatter.trigger_word,
            "phases": [p.to_dict() for p in self.phases],
            "loop": [s.to_dict() for s in self.loop],
            "prompts": self.prompts,
            "phase_scripts": self.phase_scripts,
            "state_fields": self.state_fields or [],
            "generated_at": self.generated_at,
        }


@dataclass
class ValidationReport:
    """编译器校验结果"""
    overall_score: int = 0               # 0-100
    checks: list[dict] = field(default_factory=list)  # [{name, passed, detail}]
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_check(self, name: str, passed: bool, score: int = 0, detail: str = ""):
        self.checks.append({"name": name, "passed": passed, "score": score, "detail": detail})

    def finalize(self):
        self.overall_score = sum(c.get("score", 0) for c in self.checks if c["passed"])
        self.passed = all(c["passed"] for c in self.checks)


# ═══════════════════════════════════════════════════════════
# 运行时游戏状态
# ═══════════════════════════════════════════════════════════

@dataclass
class TurnRecord:
    """单轮记录"""
    turn: int
    narrative: str = ""
    player_input: str = ""
    phase: str = ""

    def to_dict(self) -> dict:
        return {"turn": self.turn, "narrative": self.narrative,
                "player_input": self.player_input, "phase": self.phase}


@dataclass
class GameState:
    """运行时通用游戏状态。custom 字典承载生成游戏的特有字段。"""
    turn: int = 1
    day: int = 1
    phase: str = ""
    player_location: str = ""
    player_name: str = "你"
    custom: dict = field(default_factory=dict)
    history: list[TurnRecord] = field(default_factory=list)
    npcs: dict = field(default_factory=dict)       # {id: {name, affection, location, status}}
    inventory: list[str] = field(default_factory=list)
    active_events: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)  # 长对话摘要块
    lorebook_state: dict = field(default_factory=dict)   # 动态条目持久化
    last_input: str = ""
    created_at: str = ""
    updated_at: str = ""

    def add_log(self, msg: str):
        """非玩家可见的系统日志"""
        pass  # 转为通过 logger 记录

    def get_recent_turns(self, n: int) -> str:
        """获取最近 N 轮的叙事，用于协议检查和摘要"""
        recent = self.history[-n:]
        parts = []
        for r in recent:
            parts.append(f"[轮{r.turn}] 玩家: {r.player_input}\n叙事: {r.narrative[:300]}")
        return "\n".join(parts)

    def add_flag(self, flag: str):
        if flag not in self.flags:
            self.flags.append(flag)

    def has_flag(self, flag: str) -> bool:
        return flag in self.flags

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "day": self.day,
            "phase": self.phase,
            "player_location": self.player_location,
            "player_name": self.player_name,
            "custom": self.custom,
            "npcs": self.npcs,
            "inventory": self.inventory,
            "active_events": self.active_events,
            "flags": self.flags,
            "summaries": self.summaries,
            "lorebook_state": self.lorebook_state,
            "last_input": self.last_input,
            "created_at": self.created_at or time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "history": [r.to_dict() for r in self.history],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        return cls(
            turn=d.get("turn", 1),
            day=d.get("day", 1),
            phase=d.get("phase", ""),
            player_location=d.get("player_location", ""),
            player_name=d.get("player_name", "你"),
            custom=d.get("custom", {}),
            npcs=d.get("npcs", {}),
            inventory=d.get("inventory", []),
            active_events=d.get("active_events", []),
            flags=d.get("flags", []),
            summaries=d.get("summaries", []),
            lorebook_state=d.get("lorebook_state", {}),
            last_input=d.get("last_input", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            history=[TurnRecord(**r) if isinstance(r, dict) else r for r in d.get("history", [])],
        )


# ═══════════════════════════════════════════════════════════
# 默认值
# ␐══════════════════════════════════════════════════════════

DEFAULT_LOOP = [
    LoopStep(1, "read_state"),
    LoopStep(2, "route", {"route": {}}),
    LoopStep(3, "tool", {"tool": "{routed_tool}"}),
    LoopStep(4, "llm_narrative", {"prompt_key": "narrative_prompt"}),
    LoopStep(5, "pause"),
    LoopStep(6, "llm_process", {"prompt_key": "process_prompt"}),
    LoopStep(7, "write_state"),
]

ENTRY_TYPE_DEFAULTS = {
    "setting":    {"strategy": "constant", "priority": 9999, "position": "after_agents"},
    "rule":       {"strategy": "normal",   "priority": 50,   "position": "after_agents"},
    "npc":        {"strategy": "normal",   "priority": 20,   "position": "after_instr"},
    "location":   {"strategy": "normal",   "priority": 15,   "position": "after_instr"},
    "item":       {"strategy": "normal",   "priority": 10,   "position": "after_instr"},
    "faction":    {"strategy": "normal",   "priority": 15,   "position": "after_instr"},
    "event":      {"strategy": "selective","priority": 5,    "position": "after_state"},
    "summary":    {"strategy": "selective","priority": 3,    "position": "after_state"},
}

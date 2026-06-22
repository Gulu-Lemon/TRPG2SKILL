"""
多阶段 LLM 分析器 — 综合阶段 + 工具 + 校验
"""
import json
from typing import OrderedDict

from core.state import (
    SchemaAnalysis, EntitySet, MechanicsDef, NarrativeStructure,
    RulesDef, RandomnessNeeds,
)

# ═══════════════════ Phase A: 综合分析（实体+规则+结构） ═══════════════════

COMPREHENSIVE_PROMPT = """你是 TRPG 剧本分析师。请阅读以下世界书全文，完成三项分析任务，并输出一个 JSON。

你要像一个真正的 GM 那样理解这个游戏：它有怎样的世界观、运行在什么时间线上、角色是谁、规则是什么。你有充分的自由裁量权来区分这些概念。

## 任务 1: 实体与元信息

提取所有命名实体：
- game_name / genre / tone: 从标题和首段获取
- npcs: [{name, age, appearance, personality, background, location, role}]。每次出现人名、代号、称号都提取。缺项填"未知"。
- locations: [{name, type, description, features, connected_to}]
- items: [{name, description, effects}]。原文是编号/项目符号列表的，逐项列出而非概括。叙事描述的按原文信息量如实提取。
- factions: [{name, description, members}]

**注意**：原文已经被切分为章节并直接提供给你了。输出中**不需要**再输出 `section_texts`，把所有输出预算留给更重要的实体、规则和阶段提取。

## 任务 2: 规则与约束

提取所有行为约束：
- absolute_bans: [{title, text, priority}]。扫描含"禁止/严禁/绝对不/必须/应当"的句子。priority: 10=行动权隔离, 8=全局用词/叙事风格, 5=特定场景约束, 3=可选建议。
- phase_constraints: {"阶段名": ["约束文本1"]}。只在特定阶段/场景生效的规则。

## 任务 3: 游戏阶段与结构

分析游戏的时间线结构。注意区分三类结构——只把第一类提取为 phases：

**时间线阶段（提取为 phases）**：
- 游戏从开始到结束依次经历的状态
- 有明确的先后顺序和转换条件
- 字段: [{name, next, condition}]
- condition 必须是机器可判断的表达式，仅支持：turn > X、turn >= X、has_flag('xxx')
  示例："turn > 1"（经过1轮后触发）、"turn > 3"（经过3轮后触发）。
  对于序章的多幕，用递增的 turn 条件：ACT1→ACT2 用 "turn > 1"、ACT2→ACT3 用 "turn > 2"。
  绝对不要用自然语言描述条件。
- 注意：日常时间循环（如"课间/午休/放学后"）是时间路由系统，用 time_block_system 字段记录而非 phases
- 无明确阶段则 phases 留空，mapper 会自动创建 MAIN

**序章多幕处理**：
- 原文序章有明确的多幕结构（如 5.1/5.2/5.3 或"第一幕/第二幕"）时，每幕创建一个独立 phase
- 每个 phase 的 phase_scripts 包含该幕的完整步骤指令
- 幕之间有明确的用户交互触发点（用户输入后自动流转到下一幕）
- 每幕的 condition 用 turn > N（N 递增：第1幕 turn>1、第2幕 turn>2）
- 如果原文序章只是单段描述无分幕，则用一个 PROLOGUE 阶段即可

**内部状态机（放入对应 phase 的 phase_scripts 中）**：
- NPC 反应阶段、战斗阶段等
- 不是游戏时间线，而是某个 phase 内部的触发-响应逻辑

机制：dice_system, has_affection, has_inventory, time_system, time_block_system, day_night_cycle。

## 输出 JSON
{
  "game_name": "...", "genre": "...", "tone": "...",
  "npcs": [...], "locations": [...], "items": [...], "factions": [...],
  "absolute_bans": [...], "phase_constraints": {...},
  "phases": [...], "phase_scripts": {"PROLOGUE": [...], "MAIN": [...]},
  "time_system": "none", "time_block_system": "", "day_night_cycle": false,
  "dice_system": "none", "has_affection": false, "has_inventory": false,
  "player_style": "player_driven",
  "need_npc_roller": false, "need_event_roller": false,
  "need_location_roller": false, "need_item_roller": false
}
"""

# ═══════════════════ Phase B: 工具 ═══════════════════

TOOLS_PROMPT = """你是 TRPG 数据提取工。根据以下世界书和已提取的实体信息，判断游戏需要哪些 Python 工具脚本。

## 已提取的信息
{entity_summary}

## 数据池
原文中需要"随机抽取/随机选择"的列表数据（物品表、抽卡池、遭遇表等），逐项记录名称和关键属性。原文明确说"可以自由创作"的部分不做强制提取；但原文给出了具体列表的，尽量完整记录。

## 输出
{{
  "tool_specs": [
    {{
      "filename": "candy_roller.py",
      "description": "从糖果数据库随机抽取",
      "data_pool": [
        {{"name": "爆浆葡萄软糖", "effect": "潮吹特化"}}
      ]
    }}
  ]
}}

如果原文确实没有需要生成工具的数据，tool_specs 返回空数组。
"""

# ═══════════════════ Phase C: 校验 ═══════════════════

VALIDATE_PROMPT = """你是 TRPG 编译结果审计官。核心原则：**忠于原文**。原文严格的地方严格检查，原文留有余地的地方宽容对待。揣测原文作者的意图来做判断。

## 已提取的分析结果
{analysis_summary}

## 检查清单

### 禁令审计
原文中"禁止/严禁"的语句在 absolute_bans 中是否都有对应？text 是原文引用还是改写？
有没有把阶段约束误标为全局禁令？

### 实体审计
原文的命名角色/地点/物品是否都在对应数组中？原文是编号列表的（≥5项），items 中是否至少覆盖了大部分？

### 阶段审计
- phases 的数量是否和原文的章节/部分结构大致对应？
- 是否把内部状态机（如 NPC 反应阶段、战斗解说阶段）误标为时间线阶段？
- 原文明确有序章/开幕的，是否创建了对应阶段？
- 如果有 5+ 节的编号系统（如 §3.1-3.5），确认它是内部状态机而非游戏阶段

### 数据池审计
原文中需要随机抽取的数据列表是否提取到了 tool_specs？原文说"自由发挥/AI自行创作"的部分，允许空数据池。

### 代码语法审计
检查生成的 Python 工具脚本语法是否正确。

## 输出
{{
  "passed": true/false,
  "score": 0-100,
  "errors": [
    {{"phase": 1, "field": "npcs", "issue": "...", "fix": "..."}}
  ]
}}
phase 字段: 1=综合(实体/规则/结构), 2=工具
"""

# ═══════════════════ 从综合结果提取 SchemaAnalysis ═══════════════════

def comprehensive_to_analysis(d: dict, sections: list = None) -> SchemaAnalysis:
    """从综合分析结果构建 SchemaAnalysis。sections 从 parser 直接传入，不走 LLM。"""

    def _arr(v):
        return v if isinstance(v, list) else []

    return SchemaAnalysis(
        game_name=d.get("game_name") or "未命名游戏",
        genre=d.get("genre") or "",
        tone=d.get("tone") or "",
        player_style=d.get("player_style") or "player_driven",
        entities=EntitySet(
            world_summary=d.get("world_summary") or f"《{d.get('game_name', '未命名游戏')}》",
            npcs=_arr(d.get("npcs")),
            locations=_arr(d.get("locations")),
            items=_arr(d.get("items")),
            factions=_arr(d.get("factions")),
            sections=sections or _arr(d.get("section_texts")),
        ),
        mechanics=MechanicsDef(
            dice_system=d.get("dice_system") or "",
            skill_checks=_arr(d.get("skill_checks")),
            status_effects=_arr(d.get("status_effects")),
            affection_system=bool(d.get("has_affection")),
            inventory_system=bool(d.get("has_inventory")),
            time_system=d.get("time_system") or "",
        ),
        narrative=NarrativeStructure(
            has_prologue=bool(d.get("has_prologue")),
            prologue_scenes=int(d.get("prologue_scenes") or 0),
            phases=_arr(d.get("phases")),
            phase_scripts=d.get("phase_scripts") or {},
            day_night_cycle=bool(d.get("day_night_cycle")),
            time_block_system=d.get("time_block_system") or "",
            player_style=d.get("player_style") or "player_driven",
        ),
        rules=RulesDef(
            absolute_bans=_arr(d.get("absolute_bans")),
            phase_constraints=d.get("phase_constraints") or {},
            background_knowledge=_arr(d.get("background_knowledge")),
        ),
        randomness=RandomnessNeeds(
            need_npc_roller=bool(d.get("need_npc_roller")),
            need_event_roller=bool(d.get("need_event_roller")),
            need_location_roller=bool(d.get("need_location_roller")),
            need_item_roller=bool(d.get("need_item_roller")),
        ),
        state_fields=_arr(d.get("state_fields")),
    )

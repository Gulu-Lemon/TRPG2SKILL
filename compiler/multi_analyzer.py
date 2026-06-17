"""
多阶段 LLM 分析器 — 每阶段单任务，校验+自动修正
"""
import json
from typing import OrderedDict

from core.state import (
    SchemaAnalysis, EntitySet, MechanicsDef, NarrativeStructure,
    RulesDef, RandomnessNeeds,
)

# ═══════════════════ Phase 1: 实体提取 ═══════════════════

ENTITY_PROMPT = """你是 TRPG 实体提取器。扫描以下世界书全文，提取所有命名实体。

## 游戏元信息
- game_name: 从标题/文档名提取游戏名
- genre: 奇幻/科幻/都市/校园/武侠等
- tone: 轻松/黑暗/悬疑/喜剧/浪漫等

## 角色 (npcs)
每次出现人名、代号、称号都提取为独立条目。字段: {name, age, appearance, personality, background, location, role}。缺项填"未知"。

## 地点 (locations)
每个命名场景/区域/建筑。字段: {name, type, description, features, connected_to}。

## 物品 (items)
每个有名称的道具/武器/消耗品/货币。字段: {name, description, effects}。
原文中是编号/项目符号列表的（如 §1 §2 §3 或 1. 2. 3.），尽可能逐项列出而非用一两句话概括。原文本身是叙事描述的，按原文信息量如实提取即可。

## 势力 (factions)
每个有名称的组织/团体/阵营。字段: {name, description, members}。

## 原文归档 (section_texts)
按原文章节切分，完整保留原文。text 逐字引用。字段: [{title, text}]。

输出 JSON:
{
  "game_name": "游戏名", "genre": "类型", "tone": "基调",
  "npcs": [...], "locations": [...], "items": [...], "factions": [...],
  "section_texts": [{"title": "...", "text": "原文全文..."}]
}
"""


RULES_PROMPT = """你是 TRPG 规则提取器。扫描世界书全文，提取所有约束规则。

## 全局禁令 (absolute_bans, 每轮输出必须遵守)
扫描含"禁止/严禁/绝对不/必须/应当"的句子。字段: {title: "简短概括", text: "原文完整句子", priority: 1-10}。
priority: 10=行动权隔离, 8=全局用词/叙事风格, 5=特定场景约束, 3=可选建议。
每轮必须遵守的放这里，阶段特有的放 phase_constraints。

## 阶段约束 (phase_constraints)
只在特定阶段/场景生效的规则。格式: {"阶段名": ["约束文本1", "约束文本2"]}。

输出 JSON:
{
  "absolute_bans": [{"title": "...", "text": "...", "priority": 5}],
  "phase_constraints": {"CHAPTER1": ["仅第一章生效的约束"]}
}
"""


STRUCTURE_PROMPT = """你是 TRPG 结构分析师。扫描世界书全文，提取游戏结构和机制。

## 阶段 (phases)
对照原文章节/阶段标题提取。字段: [{name, next, condition}]。有序章/开幕文字则创建 PROLOGUE。原文编号的章节尽量按编号命名。无明确阶段则留空。

## 阶段脚本 (phase_scripts)
对每个阶段，提取原文中该阶段的行为指令。key 必须和 phases 的 name 一致，无阶段时用 "MAIN"。保留原文的步骤编号和顺序（如"第一阶段""第二步"）。原文有物品列表/菜单的，生成指令提醒从已有数据中选择。

## 时间系统
time_system: "day_night"/"time_blocks"/"none"。如有具体时间段名称则填入 time_block_system。

## 机制
dice_system/has_affection/has_inventory：根据原文如实记录。

输出 JSON:
{
  "phases": [], "phase_scripts": {},
  "time_system": "none", "time_block_system": "", "day_night_cycle": false,
  "dice_system": "none", "has_affection": false, "has_inventory": false
}
"""


TOOLS_PROMPT = """你是 TRPG 数据提取工。扫描原文全文，找出需要随机抽取或查询的数据列表。

## 数据池
原文中需要"随机抽取/随机选择"的列表数据（物品表、抽卡池、遭遇表等），逐项记录名称和关键属性。原文明确说"可以自由创作"的部分不做强制提取；但原文给出了具体列表的，尽量完整记录。

不需要随机抽取但希望 LLM 查询的静态列表（如所有糖果列表供叙事参考），也可以生成 tool 供 agent 调用。

## 输出
{
  "tool_specs": [
    {
      "filename": "candy_roller.py",
      "description": "从糖果数据库随机抽取",
      "data_pool": [
        {"name": "爆浆葡萄软糖", "effect": "潮吹特化，改变体液渗透压"},
        {"name": "海盐香草焦糖", "effect": "催乳反应"}
      ]
    }
  ]
}

如果原文确实没有需要生成工具的数据，tool_specs 返回空数组。
"""


VALIDATE_PROMPT = """你是 TRPG 编译结果审计官。核心原则：**忠于原文**。原文严格的地方严格检查，原文留有余地的地方宽容对待。揣测原文作者的意图来做判断。

## 检查清单

### 禁令审计
原文中"禁止/严禁"的语句在 absolute_bans 中是否都有对应？text 是原文引用还是改写？
有没有把阶段约束误标为全局禁令？

### 实体审计
原文的命名角色/地点/物品是否都在对应数组中？原文是编号列表的（≥5项），items 中是否至少覆盖了大部分？
原文是叙事描述的，不过度拆分。

### 阶段审计
phases 和原文的章节标题是否大致对应？转换条件原文中能找到依据吗？
原文明确有序章/开幕的，是否创建了对应阶段？原文没有明确阶段结构的，不强制拆分。

### 数据池审计
原文中需要随机抽取的数据列表是否提取到了 tool_specs？原文说"自由发挥/AI自行创作"的部分，允许空数据池。

### 代码语法审计
检查生成的 Python 工具脚本语法是否正确（是否有明显错误如未闭合括号、缺import等）。

## 输出
{
  "passed": true/false,
  "score": 0-100,
  "errors": [
    {"phase": 1, "field": "npcs", "issue": "...", "fix": "..."}
  ]
}
phase 字段对应: 1=实体, 2=规则, 3=结构, 4=工具
"""


# ═══════════════════ 合并 ═══════════════════

def merge_results(entity: dict, rules: dict, structure: dict, tools: dict) -> SchemaAnalysis:
    """合并四个 Phase 的结果为完整 SchemaAnalysis"""

    def _arr(v):
        return v if isinstance(v, list) else []

    return SchemaAnalysis(
        game_name=entity.get("game_name") or "未命名游戏",
        genre=entity.get("genre") or "",
        tone=entity.get("tone") or "",
        player_style=structure.get("player_style") or "player_driven",
        entities=EntitySet(
            world_summary=entity.get("world_summary") or f"《{entity.get('game_name', '未命名游戏')}》",
            npcs=_arr(entity.get("npcs")),
            locations=_arr(entity.get("locations")),
            items=_arr(entity.get("items")),
            factions=_arr(entity.get("factions")),
            sections=_arr(entity.get("section_texts")),
        ),
        mechanics=MechanicsDef(
            dice_system=structure.get("dice_system") or "",
            skill_checks=_arr(structure.get("skill_checks")),
            status_effects=_arr(structure.get("status_effects")),
            affection_system=bool(structure.get("has_affection")),
            inventory_system=bool(structure.get("has_inventory")),
            time_system=structure.get("time_system") or "",
        ),
        narrative=NarrativeStructure(
            has_prologue=bool(structure.get("has_prologue")),
            prologue_scenes=int(structure.get("prologue_scenes") or 0),
            phases=_arr(structure.get("phases")),
            phase_scripts=structure.get("phase_scripts") or {},
            day_night_cycle=bool(structure.get("day_night_cycle")),
            time_block_system=structure.get("time_block_system") or "",
            player_style=structure.get("player_style") or "player_driven",
        ),
        rules=RulesDef(
            absolute_bans=_arr(rules.get("absolute_bans")),
            phase_constraints=rules.get("phase_constraints") or {},
            background_knowledge=_arr(rules.get("background_knowledge")),
        ),
        randomness=RandomnessNeeds(
            need_npc_roller=False,
            need_event_roller=False,
            need_location_roller=False,
            need_item_roller=False,
        ),
        state_fields=_arr(structure.get("state_fields")),
        tool_specs=_arr(tools.get("tool_specs")),
    )

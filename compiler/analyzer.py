"""
LLM 分析器 — 结构化单轮 Prompt，引导逐步提取
"""
from typing import OrderedDict

from core.state import (
    SchemaAnalysis, EntitySet, MechanicsDef, NarrativeStructure,
    RulesDef, RandomnessNeeds,
)

ANALYSIS_PROMPT = """你是 TRPG 编译器分析师。分析以下世界书，按步骤逐步提取信息。

## 步骤 1: 元信息
- game_name: 从标题/文档名提取游戏名
- genre: 奇幻/科幻/都市/校园/武侠/其他
- tone: 轻松/黑暗/悬疑/喜剧/浪漫/恐怖/史诗
- player_style: 大部分时间等待玩家输入选 player_driven，有固定剧情线选 story_driven

## 步骤 2: 实体提取
仔细扫描全文，提取所有命名实体：
- npcs: [{name, age, appearance, personality, background, location, role}]
- locations: [{name, type, description, features, connected_to}]
- items: [{name, description, effects}]
- factions: [{name, description, members}]

角色名必须在原文中有明确出现。不要编造。缺项填"未知"。

## 步骤 3: 规则提取
扫描含"禁止/严禁/绝对不/必须/应当"等词的行。原文逐字提取为:
- absolute_bans: [{title: "简短标题", text: "原文完整句子"}]
每条禁令的 title 概括其含义，text 逐字引用。

## 步骤 4: 阶段与时间
对照原文的章节/阶段标题：
- phases: [{name: "阶段名", next: "下一阶段", condition: "转换条件"}]
- 如果有"序章/开幕/第X章"等，用对应名称
- 无明确阶段填 null（MAPPER 会自动创建 MAIN）
- time_system: 白天/夜晚 填 day_night，课间/时间段 填 time_blocks，无填 none
- time_block_system: "课间/午休/放学后"这样的字符串

## 步骤 5: 机制与随机
- dice_system: d20/d6/none
- has_affection: 有好感度系统填 true
- has_inventory: 有物品/背包系统填 true
- need_npc_roller: 有"随机NPC/随机抽取角色"填 true
- need_event_roller: 有"随机事件/事件池"填 true
- need_location_roller: 有"随机地点/随机探索"填 true
- need_item_roller: 有"随机道具/随机物品"填 true
- state_fields: 识别需跨对话保存的状态字段 [{name, type, default}]

## 步骤 6: 输出
将以上全部信息合并为一个 JSON 对象输出。没有信息的字段用默认值（空数组/空字符串/null）。
注意：npcs/locations/items 即使原文只有零散描述也要尝试提取。不要遗漏。
"""


def analyze(sections: OrderedDict[str, str], llm, feedback: str = "") -> SchemaAnalysis:
    full_text = "\n\n".join(
        f"## {title}\n{text}" for title, text in sections.items()
    )

    extra = ""
    if feedback:
        extra = f"\n\n## 用户修正意见（必须遵守）\n{feedback}"

    try:
        result = llm.chat_json(
            messages=[{"role": "user", "content": full_text + extra}],
            system=ANALYSIS_PROMPT,
            temperature=0.3,
            max_tokens=4000,
        )
    except Exception as e:
        print(f"    [WARN] 分析失败: {e}")
        return SchemaAnalysis(game_name="未命名游戏")

    return _dict_to_analysis(result)


def _dict_to_analysis(d: dict) -> SchemaAnalysis:
    # 标准化 null 值 → 空数组/空字符串
    def _arr(v): return v if isinstance(v, list) else []
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
            sections=[],
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
            npc_pool=_arr(d.get("npc_pool")),
            event_pool=_arr(d.get("event_pool")),
            location_pool=_arr(d.get("location_pool")),
            item_pool=_arr(d.get("item_pool")),
        ),
        state_fields=_arr(d.get("state_fields")),
    )

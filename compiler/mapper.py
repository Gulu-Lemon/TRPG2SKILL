"""
Schema 映射器 — 将 SchemaAnalysis 转换为 SkillSpec（纯代码，无 LLM 调用）
"""
from core.state import (
    SchemaAnalysis, SkillSpec, FrontmatterSpec, PhaseSpec,
    LoopStep, LorebookEntry, LorebookStrategy, InsertPosition,
    DEFAULT_LOOP, ENTRY_TYPE_DEFAULTS,
)
import time


MAX_AGENTS_TOKENS = 800  # AGENTS.md 硬上限

def map_to_spec(analysis: SchemaAnalysis) -> SkillSpec:
    """SchemaAnalysis → SkillSpec"""

    # 1. Frontmatter
    trigger_word = f"{analysis.game_name}，启动！"
    frontmatter = FrontmatterSpec(
        name=analysis.game_name,
        trigger_word=trigger_word,
        description=f"AI驱动的TRPG: {analysis.game_name}。{analysis.tone}风格的{analysis.genre}游戏。",
    )

    # 2. Phases
    phases = _build_phases(analysis.narrative.phases)

    # 3. Loop
    loop = _build_loop(analysis, phases)

    # 4. AGENTS.md rules
    agents_md_rules = _build_agents_rules(analysis)

    # 5. Lorebook entries
    lorebook_entries = _build_lorebook_entries(analysis)

    # 6. Reference files
    reference_files = _build_reference_files(analysis)

    # 7. Tools
    tools = _build_tools(analysis)

    # 8. Prompts
    prompts = _build_prompts(analysis)

    return SkillSpec(
        frontmatter=frontmatter,
        phases=phases,
        loop=loop,
        agents_md_rules=agents_md_rules,
        lorebook_entries=lorebook_entries,
        reference_files=reference_files,
        tools=tools,
        state_fields=analysis.state_fields,
        prompts=prompts,
        phase_scripts=getattr(analysis.narrative, 'phase_scripts', {}) or {},
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _build_phases(phase_dicts: list[dict]) -> list[PhaseSpec]:
    phases = []
    for p in phase_dicts:
        phases.append(PhaseSpec(
            name=p.get("name", ""),
            next_phase=p.get("next"),
            condition=p.get("condition", ""),
        ))
    if not phases:
        phases = [PhaseSpec("MAIN")]
    return phases


def _build_loop(analysis, phases) -> list[LoopStep]:
    loop = [LoopStep(s.step, s.type, dict(s.params)) for s in DEFAULT_LOOP]

    # 根据游戏特性调整循环
    if analysis.narrative.day_night_cycle:
        for s in loop:
            if s.type == "route":
                s.params["route"] = {
                    "day": {"next_step": 3, "tool": "event_roller.py --day"},
                    "night": {"next_step": 3, "tool": "event_roller.py --night"},
                }
    elif analysis.narrative.time_block_system:
        blocks = analysis.narrative.time_block_system
        route = {}
        for block in blocks.split("/"):
            block = block.strip()
            if block:
                route[block] = {"next_step": 3}
        if route:
            for s in loop:
                if s.type == "route":
                    s.params["route"] = route

    # 检查是否有可路由的工具
    has_tools = bool(getattr(analysis, 'tool_specs', []))
    needs_roller = analysis.randomness.need_event_roller
    has_route_tools = any(
        entry.get("tool")
        for s in loop if s.type == "route"
        for entry in s.params.get("route", {}).values()
    )
    if not has_tools and not needs_roller and not has_route_tools:
        for s in loop:
            if s.type == "tool":
                s.type = "llm_narrative"
                s.params["prompt_key"] = "narrative_prompt"

    return loop


def _build_agents_rules(analysis) -> list[dict]:
    rules = []
    demoted = []

    for ban in analysis.rules.absolute_bans:
        text = ban.get("text", str(ban))
        title = ban.get("title", f"禁令{len(rules)+1}")
        priority = ban.get("priority", 10)
        rule = {"title": title, "text": text, "priority": priority}
        rules.append(rule)

    # Token 限制检查
    total = sum(len(r["title"]) + len(r["text"]) for r in rules)
    if total // 2 > MAX_AGENTS_TOKENS:
        rules.sort(key=lambda r: r["priority"], reverse=True)
        selected = []
        used = 0
        for rule in rules:
            tokens = (len(rule["title"]) + len(rule["text"])) // 2
            if used + tokens <= MAX_AGENTS_TOKENS:
                selected.append(rule)
                used += tokens
            else:
                demoted.append(rule)
        rules = selected

    # 补充标准约束
    if analysis.player_style == "player_driven":
        rules.append({
            "title": "行动权隔离",
            "text": "绝对禁止：代操玩家角色。所有叙事必须在玩家行动点暂停，等待玩家输入后再继续。",
            "priority": 0,
        })
    rules.append({
        "title": "叙事风格",
        "text": f"绝对禁止：使用网文隐喻或现代流行语。保持{analysis.tone}氛围。",
        "priority": 0,
    })
    if _detect_procedural_content(analysis):
        rules.append({
            "title": "禁止编造",
            "text": "绝对禁止：虚构Lorebook中已有实体的名称、属性或效果。但世界书明确授权即兴生成的内容（如盲盒抽取、随机NPC生成、事件池等），可在规则约束范围内合理生成。",
            "priority": 9,
        })
    else:
        rules.append({
            "title": "禁止编造",
            "text": "绝对禁止：自行编造物品名称、角色姓名、地点名称。所有实体名称必须来自世界书原文（Lorebook中已存储），不得虚构不存在的名称、属性或效果。",
            "priority": 9,
        })

    return rules


def _detect_procedural_content(analysis) -> bool:
    """检测世界书是否以生成式内容（盲盒/随机NPC/事件池）为核心"""
    tool_specs = getattr(analysis, 'tool_specs', []) or []
    for ts in tool_specs:
        if ts.get("data_pool"):
            return True
    sections = analysis.entities.sections
    procedural_kw = ["随机", "盲盒", "抽取", "即兴", "生成引擎", "生成机制", "随机抽取"]
    for s in sections:
        text = s.get("text", "") + s.get("title", "")
        if any(kw in text for kw in procedural_kw):
            return True
    ws = analysis.entities.world_summary or ""
    if any(kw in ws for kw in procedural_kw):
        return True
    return False


def _build_lorebook_entries(analysis) -> list[LorebookEntry]:
    entries = []

    # 世界观（constant）
    if analysis.entities.world_summary:
        entries.append(LorebookEntry(
            id="setting_world",
            title="世界总观",
            content=analysis.entities.world_summary,
            type="setting",
            keys=[],
            strategy=LorebookStrategy.CONSTANT,
            position=InsertPosition.AFTER_AGENTS,
            priority=9999,
        ))

    # 角色
    for i, npc in enumerate(analysis.entities.npcs):
        name = npc.get("name", f"未知角色{i}")
        content_parts = [name]
        if npc.get("age"): content_parts.append(f"{npc['age']}岁")
        if npc.get("appearance"): content_parts.append(npc["appearance"])
        if npc.get("personality"): content_parts.append(npc["personality"])
        if npc.get("background"): content_parts.append(npc["background"])

        keys = [name]
        defaults = ENTRY_TYPE_DEFAULTS["npc"]

        entries.append(LorebookEntry(
            id=f"npc_{i}",
            title=name,
            content="。".join(content_parts) + "。",
            type="npc",
            keys=keys,
            strategy=LorebookStrategy(defaults["strategy"]),
            position=InsertPosition(defaults["position"]),
            priority=defaults["priority"],
        ))

    # 地点
    for i, loc in enumerate(analysis.entities.locations):
        name = loc.get("name", f"未知地点{i}")
        content_parts = [name]
        if loc.get("description"): content_parts.append(loc["description"])
        if loc.get("features"): content_parts.append(f"特征: {loc['features']}")

        keys = [name]
        defaults = ENTRY_TYPE_DEFAULTS["location"]

        entries.append(LorebookEntry(
            id=f"loc_{i}",
            title=name,
            content="。".join(content_parts) + "。",
            type="location",
            keys=keys,
            strategy=LorebookStrategy(defaults["strategy"]),
            position=InsertPosition(defaults["position"]),
            priority=defaults["priority"],
        ))

    # 物品
    for i, item in enumerate(analysis.entities.items):
        name = item.get("name", f"未知物品{i}")
        content_parts = [name]
        if item.get("description"): content_parts.append(item["description"])
        if item.get("effects"): content_parts.append(f"效果: {item['effects']}")

        keys = [name]
        defaults = ENTRY_TYPE_DEFAULTS["item"]

        entries.append(LorebookEntry(
            id=f"item_{i}",
            title=name,
            content="。".join(content_parts) + "。",
            type="item",
            keys=keys,
            strategy=LorebookStrategy(defaults["strategy"]),
            position=InsertPosition(defaults["position"]),
            priority=defaults["priority"],
        ))

    # 势力
    for i, fac in enumerate(analysis.entities.factions):
        name = fac.get("name", f"未知势力{i}")
        entries.append(LorebookEntry(
            id=f"faction_{i}",
            title=name,
            content=fac.get("description", ""),
            type="faction",
            keys=[name],
            strategy=LorebookStrategy.NORMAL,
            position=InsertPosition.AFTER_INSTRUCTION,
            priority=ENTRY_TYPE_DEFAULTS["faction"]["priority"],
        ))

    # 核心规则（降级到 lorebook 的规则）
    for i, ban in enumerate(analysis.rules.absolute_bans):
        entries.append(LorebookEntry(
            id=f"rule_{i}",
            title=ban.get("title", f"规则{i+1}"),
            content=ban.get("text", str(ban)),
            type="rule",
            keys=[],
            strategy=LorebookStrategy.NORMAL,
            position=InsertPosition.AFTER_AGENTS,
            priority=ENTRY_TYPE_DEFAULTS["rule"]["priority"],
        ))

    return entries


def _build_reference_files(analysis) -> list[dict]:
    """按主题切分为参考文件（给人读的 .md 副本）"""
    refs = []
    sections = analysis.entities.sections

    if not sections:
        return refs

    # 按约 40 行一个文件切分
    refs_per_file_target = max(5, len(sections) // 40)
    if refs_per_file_target < 1:
        refs_per_file_target = 1

    n_files = max(1, len(sections) // refs_per_file_target)
    for i in range(n_files):
        start = i * refs_per_file_target
        end = start + refs_per_file_target if i < n_files - 1 else len(sections)
        chunk = sections[start:end]

        titles = [s.get("title", f"段落{j+1}") for j, s in enumerate(chunk)]
        filename_prefix = f"{i + 1}"
        main_title = titles[0] if titles else f"参考文件{i + 1}"
        filename = f"{filename_prefix}-{main_title[:20]}.md"

        content_lines = []
        for s in chunk:
            content_lines.append(f"## {s.get('title', '')}")
            content_lines.append(s.get("text", ""))
            content_lines.append("")

        refs.append({
            "filename": filename,
            "title": main_title,
            "content": "\n".join(content_lines),
        })

    return refs


def _build_tools(analysis) -> list[dict]:
    tools = []
    for spec in getattr(analysis, 'tool_specs', []) or []:
        tools.append({
            "filename": spec.get("filename", "tool.py"),
            "type": spec.get("description", ""),
            "data_pools": spec.get("data_pool", []),
        })

    tools.append({"filename": "session_starter.py", "type": "system"})
    tools.append({"filename": "state_cli.py", "type": "system"})
    return tools


def _build_prompts(analysis) -> dict[str, str]:
    """生成 NARRATIVE 和 PROCESS 的 System Prompt 模板"""

    npc_summary = "\n".join(
        f"- {n.get('name', '?')}: {n.get('personality', '')[:60]}"
        for n in analysis.entities.npcs[:10]
    ) if analysis.entities.npcs else "(无预设角色)"

    narrative_prompt = f"""你是《{analysis.game_name}》的 GM。

{analysis.tone}风格的{analysis.genre}故事。

## 核心规则
- 当前阶段: {{phase}}
- 玩家位置: {{location}}
- 绝对禁止代操玩家角色
- 保持{analysis.tone}氛围
- 叙事聚焦感官细节和角色互动
- {{extra_rules}}

## 当前上下文
{{lorebook_context}}

## 游戏状态
{{state_snapshot}}

## 指令
根据以上信息和对话历史，生成下一个叙事段落（300-600字）。
叙事应在关键决策点暂停，等待玩家选择或输入。
"""

    process_prompt = f"""你是《{analysis.game_name}》的状态解析器。

分析玩家输入，提取以下信息并以 JSON 返回:
{{
  "action": "玩家动作类型（explore/dialogue/use_item/move/other）",
  "target": "目标对象（NPC名/地点名/物品名/无）",
  "detail": "动作细节",
  "state_changes": {{"字段名": "新值"}},
  "narrative_hint": "给 GM 的叙事方向提示（50字以内）"
}}

玩家输入: {{player_input}}
当前状态: {{state_snapshot}}
"""

    return {
        "narrative_prompt": narrative_prompt,
        "process_prompt": process_prompt,
    }

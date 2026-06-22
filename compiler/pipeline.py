"""
编译器管线编排器 — 3 阶段 LLM 分析：综合分析 → 工具提取 → 校验+修正
"""
from pathlib import Path
import json
import time

from compiler.parser import parse_input
from compiler.mapper import map_to_spec
from compiler.generator import generate
from compiler.validator import validate
from core.config_profiles import create_llm_from_profile
from core.state import SchemaAnalysis


def compile(input_file: str, output_dir: str, feedback: str = "",
            progress_callback=None) -> str:
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    def emit(phase, progress, detail="", **extra):
        if progress_callback:
            progress_callback(phase, progress, detail, **extra)
        else:
            print(f"  [{phase}] {progress}% {detail}")

    emit("parse", 0, "解析输入...")
    sections = parse_input(str(input_path))
    full_text = "\n\n".join(f"## {t}\n{txt}" for t, txt in sections.items())
    if feedback:
        full_text += f"\n\n## 用户修正意见（必须遵守）\n{feedback}"
    emit("parse", 5, f"{len(sections)} 段落")

    llm = create_llm_from_profile(use_analyzer=True)
    import json as _json

    def call_llm(system_prompt, temperature=0.3, messages=None, max_tokens=4096):
        try:
            if messages is None:
                messages = [{"role": "user", "content": full_text}]
            return llm.chat_json(
                messages=messages, system=system_prompt,
                temperature=temperature, max_tokens=max_tokens,
            )
        except Exception as e:
            print(f"    [WARN] LLM 调用失败: {e}")
            return {}

    def make_entity_summary(d: dict) -> str:
        lines = []
        lines.append(f"游戏名: {d.get('game_name', '?')}")
        lines.append(f"类型: {d.get('genre', '?')}  基调: {d.get('tone', '?')}")
        lines.append(f"角色({len(d.get('npcs',[]))}): {', '.join(e.get('name','') for e in d.get('npcs',[])[:15])}")
        lines.append(f"地点({len(d.get('locations',[]))}): {', '.join(e.get('name','') for e in d.get('locations',[])[:10])}")
        lines.append(f"物品({len(d.get('items',[]))}): {', '.join(e.get('name','') for e in d.get('items',[])[:20])}")
        lines.append(f"阶段({len(d.get('phases',[]))}): {', '.join(p.get('name','') for p in d.get('phases',[]))}")
        lines.append(f"禁令({len(d.get('absolute_bans',[]))}): {', '.join(b.get('title','') for b in d.get('absolute_bans',[])[:10])}")
        return "\n".join(lines)

    def make_analysis_summary(d: dict) -> str:
        return _json.dumps({
            "game_name": d.get("game_name"),
            "npcs_count": len(d.get("npcs", [])),
            "locations_count": len(d.get("locations", [])),
            "items_count": len(d.get("items", [])),
            "factions_count": len(d.get("factions", [])),
            "bans_count": len(d.get("absolute_bans", [])),
            "phases": d.get("phases", []),
            "tool_specs_count": len(d.get("tool_specs", [])),
        }, ensure_ascii=False, indent=2)

    def serialize_errors(errors):
        if not errors: return ""
        lines = []
        for e in errors[:10]:
            lines.append(f"- Phase {e.get('phase', '?')}/{e.get('field', '?')}: {e.get('issue', '?')} → {e.get('fix', '?')}")
        return "\n".join(lines)

    # ═══════════════════ Phase A: 综合分析 ═══════════════════
    emit("comprehensive", 10, "综合分析中...")
    from compiler.multi_analyzer import COMPREHENSIVE_PROMPT, comprehensive_to_analysis

    comprehensive = call_llm(COMPREHENSIVE_PROMPT, max_tokens=8192)
    emit("comprehensive", 40,
         f"游戏:{comprehensive.get('game_name','?')} "
         f"角色:{len(comprehensive.get('npcs',[]))} "
         f"阶段:{len(comprehensive.get('phases',[]))} "
         f"禁令:{len(comprehensive.get('absolute_bans',[]))}")

    # 规范化阶段条件：自然语言 → turn > 1（防 LLM 输出不规范条件）
    import re
    _has_chinese = re.compile(r'[\u4e00-\u9fff]')
    for phase in comprehensive.get("phases", []):
        cond = phase.get("condition", "")
        if cond and _has_chinese.search(cond):
            old_cond = cond
            phase["condition"] = "turn > 1"
            print(f"  [WARN] 阶段 {phase.get('name','?')} 的条件 '{old_cond}' 不是机器可评估格式，已降级为 turn > 1")

    # ═══════════════════ Phase B: 工具 ═══════════════════
    emit("tools", 50, "分析工具需求...")
    from compiler.multi_analyzer import TOOLS_PROMPT
    entity_summary = make_entity_summary(comprehensive)
    tools_prompt = TOOLS_PROMPT.replace("{entity_summary}", entity_summary)
    tools = call_llm(tools_prompt,
                     messages=[{"role": "user", "content": full_text},
                               {"role": "user", "content": entity_summary}])
    tool_count = len(tools.get("tool_specs", []))
    emit("tools", 65, f"{tool_count} 工具")

    # 合并 → analysis（原始章节从 parser 直接传入，不走 LLM 输出）
    sections_list = [{"title": t, "text": txt} for t, txt in sections.items()]
    analysis = comprehensive_to_analysis(comprehensive, sections=sections_list)
    analysis.tool_specs = [
        ts for ts in (tools.get("tool_specs") or []) if isinstance(ts, dict)
    ]

    # ═══════════════════ Phase C: 校验 + 修正 ═══════════════════
    from compiler.multi_analyzer import VALIDATE_PROMPT
    summary = make_analysis_summary(comprehensive)
    summary_data = _json.loads(summary)
    summary_data["tool_specs_count"] = tool_count
    analysis_summary = _json.dumps(summary_data, ensure_ascii=False, indent=2)
    validate_prompt = VALIDATE_PROMPT.replace("{analysis_summary}", analysis_summary)

    max_rounds = 2
    best_analysis = analysis
    best_score = 0
    errors = []

    for round_idx in range(max_rounds + 1):
        emit("validate", 70 + round_idx * 10, "校验中...")
        validate_input = full_text + "\n\n## 当前分析结果\n" + analysis_summary
        validation = call_llm(validate_prompt + "\n\n输入数据:\n" + validate_input,
                             temperature=0.1)
        if not validation:
            emit("validate", 80, "校验调用失败")
            break

        passed = validation.get("passed", False)
        score = validation.get("score", 0)
        errors = validation.get("errors", [])
        emit("validate", 75 + round_idx * 10,
             f"{'PASS' if passed else 'FAIL'} 评分:{score} 错误:{len(errors)}")

        if score > best_score:
            best_score = score
            best_analysis = SchemaAnalysis(
                game_name=analysis.game_name, genre=analysis.genre, tone=analysis.tone,
                player_style=analysis.player_style,
                entities=analysis.entities, mechanics=analysis.mechanics,
                narrative=analysis.narrative, rules=analysis.rules,
                randomness=analysis.randomness, state_fields=analysis.state_fields,
                tool_specs=analysis.tool_specs,
            )

        if passed or round_idx >= max_rounds or not errors:
            break

        emit("correct", 75 + round_idx * 10, f"修正 {len(errors)} 个问题...")
        error_text = serialize_errors(errors)
        batch_text = f"## 上次分析的错误（必须修正）\n{error_text}"

        fixed_phases = set()
        for e in errors:
            phase_id = e.get("phase", 1)
            if phase_id in fixed_phases: continue
            fixed_phases.add(phase_id)
            if phase_id == 1:
                comprehensive = call_llm(COMPREHENSIVE_PROMPT,
                    messages=[{"role": "user", "content": full_text},
                              {"role": "user", "content": batch_text}])
                analysis = comprehensive_to_analysis(comprehensive)
            elif phase_id == 2:
                tools = call_llm(tools_prompt,
                    messages=[{"role": "user", "content": full_text},
                              {"role": "user", "content": entity_summary},
                              {"role": "user", "content": batch_text}])
                analysis.tool_specs = [
                    ts for ts in (tools.get("tool_specs") or []) if isinstance(ts, dict)
                ]

    if best_score:
        analysis = best_analysis

    if round_idx >= max_rounds and errors:
        emit("validate", 85, f"[WARN] 最佳评分:{best_score}")

    # ═══════════════════ 映射 + 生成 ═══════════════════
    emit("map", 90, "映射 Schema...")
    spec = map_to_spec(analysis)
    emit("map", 93, f"{len(spec.lorebook_entries)} 条目")

    emit("generate", 95, "生成文件...")
    generate(spec, output_path)
    emit("generate", 99, "Done")

    review_data = {
        "game_name": comprehensive.get("game_name", ""),
        "genre": comprehensive.get("genre", ""),
        "tone": comprehensive.get("tone", ""),
        "npcs": comprehensive.get("npcs", []),
        "locations": comprehensive.get("locations", []),
        "items": comprehensive.get("items", []),
        "bans": [b.get("text", "") for b in (comprehensive.get("absolute_bans") or [])],
        "phases": comprehensive.get("phases", []),
        "time_system": comprehensive.get("time_system", ""),
        "score": best_score or 0,
        "lorebook_count": len(spec.lorebook_entries),
    }
    emit("done", 100, f"'{analysis.game_name}' 评分:{best_score or '?'}%",
         review=review_data)
    llm.close()
    return str(output_path)

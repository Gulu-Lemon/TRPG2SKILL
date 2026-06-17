"""
编译器管线编排器 — 多阶段 LLM 分析 + 校验 + 自动修正
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

    def emit(phase, progress, detail=""):
        if progress_callback:
            progress_callback(phase, progress, detail)
        else:
            pct = int(progress)
            bar = "=" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"  [{bar}] {phase} {detail}")

    # ── 基础解析 ──
    emit("parse", 0, "解析输入...")
    sections = parse_input(str(input_path))
    full_text = "\n\n".join(f"## {t}\n{txt}" for t, txt in sections.items())
    if feedback:
        full_text += f"\n\n## 用户修正意见（必须遵守）\n{feedback}"
    emit("parse", 5, f"{len(sections)} 段落")

    llm = create_llm_from_profile(use_analyzer=True)
    import json as _json

    def call_llm(system_prompt, max_tokens=None, temperature=0.3, messages=None):
        try:
            if messages is None:
                messages = [{"role": "user", "content": full_text}]
            return llm.chat_json(
                messages=messages,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            print(f"    [WARN] LLM 调用失败: {e}")
            return {}

    def serialize_errors(errors):
        if not errors: return ""
        lines = []
        for e in errors[:10]:
            lines.append(f"- Phase {e.get('phase', '?')}/{e.get('field', '?')}: {e.get('issue', '?')} → {e.get('fix', '?')}")
        return "\n".join(lines)

    # ═══════════════════ Phase 1: 实体 ═══════════════════
    emit("entity", 10, "提取实体...")
    from compiler.multi_analyzer import ENTITY_PROMPT
    entity = call_llm(ENTITY_PROMPT)
    emit("entity", 20, f"{len(entity.get('npcs',[]))} 角色, {len(entity.get('locations',[]))} 地点")

    # ═══════════════════ Phase 2: 规则 ═══════════════════
    emit("rules", 25, "提取规则...")
    from compiler.multi_analyzer import RULES_PROMPT
    rules = call_llm(RULES_PROMPT)
    emit("rules", 35, f"{len(rules.get('absolute_bans',[]))} 禁令")

    # ═══════════════════ Phase 3: 结构 ═══════════════════
    emit("structure", 40, "分析结构...")
    from compiler.multi_analyzer import STRUCTURE_PROMPT
    structure = call_llm(STRUCTURE_PROMPT)
    emit("structure", 50, f"{len(structure.get('phases',[]))} 阶段")

    # ═══════════════════ Phase 4: 工具 ═══════════════════
    emit("tools", 55, "分析工具需求...")
    from compiler.multi_analyzer import TOOLS_PROMPT
    tools = call_llm(TOOLS_PROMPT)
    tool_count = len(tools.get("tool_specs", []))
    emit("tools", 65, f"{tool_count} 工具")

    # ═══════════════════ Phase 5: 校验 ═══════════════════
    from compiler.multi_analyzer import merge_results, VALIDATE_PROMPT

    analysis = merge_results(entity, rules, structure, tools)
    game_name = analysis.game_name
    entity["game_name"] = game_name  # 回传

    max_rounds = 2
    best_analysis = analysis
    best_score = 0

    for round_idx in range(max_rounds + 1):
        emit("validate", 70 + round_idx * 10, "校验中...")
        validate_input = full_text + "\n\n## 当前分析结果\n" + _json.dumps({
            "npcs": entity.get("npcs", [])[:20],
            "locations": entity.get("locations", [])[:20],
            "absolute_bans": rules.get("absolute_bans", []),
            "phases": structure.get("phases", []),
            "tool_specs": tools.get("tool_specs", []),
        }, ensure_ascii=False)

        validation = call_llm(VALIDATE_PROMPT + "\n\n输入数据:\n" + validate_input,
                             max_tokens=1500, temperature=0.1)
        if not validation:
            emit("validate", 80, "校验调用失败，跳过")
            break

        passed = validation.get("passed", False)
        score = validation.get("score", 0)
        errors = validation.get("errors", [])
        emit("validate", 75 + round_idx * 10,
             f"{'PASS' if passed else 'FAIL'} 评分:{score} 错误:{len(errors)}")

        if score > best_score:
            best_score = score
            best_analysis = merge_results(entity, rules, structure, tools)

        if passed or round_idx >= max_rounds or not errors:
            break

        # ── 自动修正（只对未通过的 Phase 重新提取）─
        emit("correct", 75 + round_idx * 10, f"修正 {len(errors)} 个问题...")
        error_text = serialize_errors(errors)
        batch_text = f"## 上次分析的错误（必须修正）\n{error_text}"
        fixed_phases = set()

        for e in errors:
            phase_id = e.get("phase", 1)
            if phase_id in fixed_phases:
                continue
            fixed_phases.add(phase_id)
            if phase_id == 1:
                entity = call_llm(ENTITY_PROMPT,
                                  messages=[{"role": "user", "content": full_text},
                                            {"role": "user", "content": batch_text}])
            elif phase_id == 2:
                rules = call_llm(RULES_PROMPT,
                                 messages=[{"role": "user", "content": full_text},
                                           {"role": "user", "content": batch_text}])
            elif phase_id == 3:
                structure = call_llm(STRUCTURE_PROMPT,
                                     messages=[{"role": "user", "content": full_text},
                                               {"role": "user", "content": batch_text}])
            elif phase_id == 4:
                tools = call_llm(TOOLS_PROMPT,
                                 messages=[{"role": "user", "content": full_text},
                                           {"role": "user", "content": batch_text}])

    # 使用最佳结果
    analysis = best_analysis

    if round_idx >= max_rounds and errors:
        emit("validate", 85,
             f"[WARN] 最佳评分:{best_score}, {len(errors)} 问题未修复")

    # ═══════════════════ Phase 7: 映射 + 生成 ═══════════════════
    emit("map", 88, "映射 Schema...")
    spec = map_to_spec(analysis)
    emit("map", 90, f"{len(spec.lorebook_entries)} 条目")

    emit("generate", 92, "生成文件...")
    generate(spec, output_path)
    emit("generate", 98, "Done")

    # 质量评分
    emit("validate", 100, "最终校验...")
    report = validate(spec, output_path, llm)
    max_score = sum(c.get("score", 0) for c in report.checks)
    pct = int(report.overall_score / max_score * 100) if max_score > 0 else 0

    emit("done", 100, f"'{game_name}' 评分:{pct}%")

    llm.close()
    return str(output_path)

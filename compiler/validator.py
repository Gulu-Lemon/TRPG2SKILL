"""
编译器校验器 — 8 维度质量评分
"""
from pathlib import Path

from core.state import SkillSpec, ValidationReport


def validate(spec: SkillSpec, output_dir: Path, llm) -> ValidationReport:
    report = ValidationReport()

    # 1. 文件完整性检查（自动，无需 LLM）
    _check_file_integrity(output_dir, report)

    # 2. AGENTS.md 检查
    _check_agents_md(spec, report)

    # 3. Loop Schema 有效
    _check_loop_schema(spec, report)

    # 4. Lorebook 合理
    _check_lorebook(spec, report)

    # 5. 工具脚本可执行
    _check_tools(output_dir, report)

    report.finalize()
    return report


def _check_file_integrity(output_dir: Path, report: ValidationReport):
    required = [
        "SKILL.md", "AGENTS.md", "loop_schema.json",
        "lorebook.json", "game_config.json",
    ]
    passed = True
    for f in required:
        path = output_dir / f
        exists = path.exists() and path.stat().st_size > 0
        if not exists:
            report.warnings.append(f"缺失文件: {f}")
            passed = False
    report.add_check("文件完整性", passed, score=10,
                     detail=f"必需文件: {len(required)}")


def _check_agents_md(spec: SkillSpec, report: ValidationReport):
    n = len(spec.agents_md_rules)
    passed = n >= 3
    report.add_check("AGENTS.md 禁令数", passed, score=8,
                     detail=f"禁令 {n} 条 (≥3 通过)")


def _check_loop_schema(spec: SkillSpec, report: ValidationReport):
    steps = spec.loop
    types = [s.type for s in steps]
    has_narrative = "llm_narrative" in types
    has_pause = "pause" in types
    has_write = "write_state" in types
    passed = has_narrative and has_pause and has_write
    report.add_check("Loop Schema", passed, score=15,
                     detail=f"{len(steps)} 步, narrative={has_narrative}, pause={has_pause}, save={has_write}")


def _check_lorebook(spec: SkillSpec, report: ValidationReport):
    entries = spec.lorebook_entries
    has_constants = any(e.strategy.value == "constant" for e in entries)
    has_normals = any(e.strategy.value == "normal" for e in entries)
    score = 0
    if has_constants: score += 5
    if has_normals: score += 3
    if len(entries) >= 3: score += 2
    passed = score >= 5
    report.add_check("Lorebook 条目", passed, score=score,
                     detail=f"{len(entries)} 条目, constant={has_constants}, normal={has_normals}")


def _check_tools(output_dir: Path, report: ValidationReport):
    import subprocess, sys
    tools_dir = output_dir / "tools"
    py_files = list(tools_dir.glob("*.py"))
    passed = len(py_files) >= 2  # session_starter + state_cli 至少
    detail = f"{len(py_files)} 个工具脚本"
    
    # 尝试导入检查每个 .py 文件有无语法错误
    for py_file in py_files:
        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                capture_output=True, timeout=5
            )
        except Exception:
            report.warnings.append(f"工具语法错误: {py_file.name}")
            passed = False
    
    report.add_check("工具脚本", passed, score=5, detail=detail)

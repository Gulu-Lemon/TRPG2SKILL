"""
诊断脚本: 对 幽灵先生 世界书运行 COMPREHENSIVE + TOOLS prompt,
保存原始 LLM 返回内容到日志，排查禁令全漏原因。
"""
import sys, json, os, re, time
from pathlib import Path

# 添加项目根
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compiler.parser import parse_input
from compiler.multi_analyzer import COMPREHENSIVE_PROMPT, TOOLS_PROMPT
from core.config_profiles import create_llm_from_profile

WORLD_BOOK = r"E:\dd\文档们\AI互动小说计划\幽灵先生：少女闺房的梦\幽灵先生：少女闺房的梦.txt"
LOG_DIR = Path(__file__).resolve().parent / ".." / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_raw(tag: str, text: str):
    safe_tag = re.sub(r'[\\/*?:"<>|]', "_", tag)
    path = LOG_DIR / f"diagnose_{safe_tag}_{int(time.time())}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"  [LOG] {tag} → {path}")
    return path

def main():
    print("=" * 60)
    print("Phase 0: LLM 抽取诊断")
    print("=" * 60)

    # 1. 解析世界书
    print("\n[1] 解析世界书...")
    sections = parse_input(WORLD_BOOK)
    print(f"  → {len(sections)} 个段落")
    for i, (title, text) in enumerate(sections.items()):
        print(f"     段落 {i}: title={title!r}  ({len(text)} 字符)")
    full_text = "\n\n".join(f"## {t}\n{txt}" for t, txt in sections.items())
    log_raw("worldbook_sections", full_text)

    # 2. 创建 LLM
    print("\n[2] 创建 LLM 客户端...")
    llm = create_llm_from_profile(use_analyzer=True)
    print(f"  → model={llm.model}")

    # 3. 调用 COMPREHENSIVE_PROMPT (原始返回 + JSON)
    print("\n[3] 调用 COMPREHENSIVE_PROMPT...")
    json_instruction = (
        "\n\n重要：你必须只输出一个有效的 JSON 对象，"
        "不要带任何 markdown 标记、解释、额外文字、或前后缀。直接输出 JSON。"
    )
    effective_system = COMPREHENSIVE_PROMPT + json_instruction
    try:
        raw_text = llm.chat(
            messages=[{"role": "user", "content": full_text}],
            system=effective_system,
            temperature=0.3,
        )
        log_raw("comprehensive_raw", raw_text)
        print(f"  → 原始返回 {len(raw_text)} 字符")
        print(f"  → 原始文本前 200 字: {raw_text[:200]}")

        # 尝试解析 JSON
        from core.llm import LLMClient
        js = LLMClient._extract_json(raw_text)
        print(f"\n  [JSON 解析成功] 字段统计:")
        print(f"     game_name:       {js.get('game_name', '?')}")
        print(f"     npcs:            {len(js.get('npcs', []))}")
        print(f"     locations:       {len(js.get('locations', []))}")
        print(f"     items:           {len(js.get('items', []))}")
        print(f"     absolute_bans:   {len(js.get('absolute_bans', []))}")
        print(f"     phases:          {len(js.get('phases', []))}")
        print(f"     phase_constraints: {len(js.get('phase_constraints', {}))}")
        print(f"     section_texts:   {len(js.get('section_texts', []))}")
        print(f"     time_system:     {js.get('time_system', '?')}")
        print(f"     time_block_system: {js.get('time_block_system', '?')}")
        print(f"     has_affection:   {js.get('has_affection', '?')}")
        print(f"     has_inventory:   {js.get('has_inventory', '?')}")
        print(f"     player_style:    {js.get('player_style', '?')}")

        if js.get("absolute_bans"):
            print(f"\n  [提取到的绝对禁令]:")
            for i, ban in enumerate(js["absolute_bans"]):
                print(f"     {i+1}. {ban.get('title', '?')}: {ban.get('text', '?')[:80]}")

        if js.get("phases"):
            print(f"\n  [提取到的阶段]:")
            for p in js["phases"]:
                print(f"     - name={p.get('name','?')} next={p.get('next','?')} condition={p.get('condition','?')[:40]}")

    except Exception as e:
        print(f"  [ERROR] COMPREHENSIVE 失败: {e}")
        js = {}

    # 4. 调用 TOOLS_PROMPT
    print("\n[4] 调用 TOOLS_PROMPT...")
    entity_summary = ""
    if js:
        lines = []
        lines.append(f"游戏名: {js.get('game_name', '?')}")
        lines.append(f"类型: {js.get('genre', '?')}  基调: {js.get('tone', '?')}")
        lines.append(f"角色({len(js.get('npcs',[]))}): {', '.join(e.get('name','') for e in js.get('npcs',[])[:15])}")
        lines.append(f"地点({len(js.get('locations',[]))}): {', '.join(e.get('name','') for e in js.get('locations',[])[:10])}")
        lines.append(f"物品({len(js.get('items',[]))}): {', '.join(e.get('name','') for e in js.get('items',[])[:20])}")
        lines.append(f"阶段({len(js.get('phases',[]))}): {', '.join(p.get('name','') for p in js.get('phases',[]))}")
        entity_summary = "\n".join(lines)
    else:
        entity_summary = "游戏名: 幽灵先生：少女闺房的梦\n(解析失败，无实体信息)"
    print(f"实体摘要:\n{entity_summary}")

    tools_prompt = TOOLS_PROMPT.replace("{entity_summary}", entity_summary)
    effective_tools = tools_prompt + json_instruction
    try:
        raw_tools = llm.chat(
            messages=[{"role": "user", "content": full_text},
                      {"role": "user", "content": entity_summary}],
            system=effective_tools,
            temperature=0.3,
            max_tokens=2048,
        )
        log_raw("tools_raw", raw_tools)
        print(f"  → 原始返回 {len(raw_tools)} 字符")
        print(f"  → 原始文本前 200 字: {raw_tools[:200]}")

        tools_js = LLMClient._extract_json(raw_tools)
        tool_count = len(tools_js.get("tool_specs", []))
        print(f"  → tool_specs: {tool_count}")
        for i, ts in enumerate(tools_js.get("tool_specs", [])):
            pool = ts.get("data_pool", [])
            print(f"     {i+1}. {ts.get('filename','?')}: {ts.get('description','?')[:60]} ({len(pool)} 条目)")
    except Exception as e:
        print(f"  [ERROR] TOOLS 失败: {e}")

    llm.close()
    print("\n[5] 完成。日志文件保存在 logs/ 目录")
    print("=" * 60)

if __name__ == "__main__":
    main()

"""
E2E 集成测试 — 验证编译器 + 运行时全链路
"""
import sys
import os
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_parser():
    """测试输入解析器"""
    from compiler.parser import parse_input
    
    sample = PROJECT_ROOT / "samples" / "candy_shop.txt"
    sections = parse_input(str(sample))
    
    assert len(sections) > 0, "解析失败: 无段落"
    print(f"  ✓ Parser: {len(sections)} 个段落")


def test_lorebook_index():
    """测试 Lorebook 关键词索引"""
    from core.state import LorebookEntry, LorebookStrategy
    from runtime.lorebook_index import LorebookIndex
    
    entries = [
        LorebookEntry(id="npc_1", title="陈震", content="黑帮头目", 
                      keys=["陈震", "刀疤脸"], strategy=LorebookStrategy.NORMAL),
        LorebookEntry(id="loc_1", title="霓虹巷", content="地下赌场",
                      keys=["霓虹巷", "赌场"], strategy=LorebookStrategy.NORMAL),
    ]
    
    idx = LorebookIndex(entries)
    
    hits = idx.scan("刀疤脸走进了赌场")
    assert "npc_1" in hits
    assert "loc_1" in hits
    print(f"  ✓ LorebookIndex: scan returns {hits}")


def test_phase_machine():
    """测试阶段状态机"""
    from core.state import GameState, PhaseSpec
    from runtime.phase_machine import PhaseMachine
    
    phases = [
        PhaseSpec("PROLOGUE", "CHAPTER1", "prologue_complete"),
        PhaseSpec("CHAPTER1", "OPEN", "day >= 3"),
        PhaseSpec("OPEN", None, ""),
    ]
    
    pm = PhaseMachine(phases)
    state = GameState(day=1, turn=1)
    
    # Should not trigger (no flag)
    assert pm.tick(state) == False
    print(f"  ✓ PhaseMachine: day=1 stays at {pm.current}")
    
    # Add flag
    state.add_flag("prologue_complete")
    assert pm.tick(state) == True
    assert pm.current == "CHAPTER1"
    print(f"  ✓ PhaseMachine: transitioned to {pm.current}")
    
    # Advance days
    state.day = 3
    assert pm.tick(state) == True
    assert pm.current == "OPEN"
    print(f"  ✓ PhaseMachine: day>=3 transitioned to {pm.current}")


def test_config_manager():
    """测试配置管理器"""
    from core.config_schema import ConfigManager, CONFIG_SCHEMA
    
    cm = ConfigManager(Path("test_config.json"))
    
    val = cm.get("lorebook.max_injection_tokens")
    print(f"  ✓ ConfigManager: lorebook.max_injection_tokens = {val}")
    
    cm.update("memory.recent_window_rounds", 20)
    assert cm.get("memory.recent_window_rounds") == 20
    print(f"  ✓ ConfigManager: updated memory.recent_window_rounds = 20")
    
    # Cleanup
    Path("test_config.json").unlink(missing_ok=True)


def test_compiler_dry_run():
    """测试编译器管线（不调 LLM）"""
    from compiler.parser import parse_input
    from compiler.mapper import map_to_spec
    from core.state import SchemaAnalysis, EntitySet, NarrativeStructure, RulesDef, RandomnessNeeds
    
    # 构造假分析结果
    analysis = SchemaAnalysis(
        game_name="测试游戏",
        genre="校园",
        tone="轻松",
        entities=EntitySet(
            world_summary="一个测试世界。",
            npcs=[{"name": "小明", "age": 12, "personality": "活泼"}],
            locations=[{"name": "教室", "description": "普通教室"}],
            items=[{"name": "糖果", "description": "普通糖果"}],
        ),
        narrative=NarrativeStructure(
            phases=[{"name": "MAIN", "next": None, "condition": ""}],
        ),
        rules=RulesDef(
            absolute_bans=[
                {"title": "禁止代操", "text": "绝对禁止代替玩家做决定。"},
                {"title": "禁止隐喻", "text": "绝对禁止使用网文隐喻。"},
                {"title": "等待输入", "text": "每次输出后必须等待玩家输入。"},
            ],
        ),
        randomness=RandomnessNeeds(),
    )
    
    spec = map_to_spec(analysis)
    
    assert spec.frontmatter.name == "测试游戏"
    assert len(spec.agents_md_rules) >= 5  # 3 original + 2 standard
    assert len(spec.lorebook_entries) >= 3  # world + npc + location + item
    assert len(spec.phases) == 1
    assert len(spec.loop) == 7
    
    print(f"  ✓ Compiler dry-run: {spec.frontmatter.name}")
    print(f"    Lorebook: {len(spec.lorebook_entries)} entries")
    print(f"    Agents.md: {len(spec.agents_md_rules)} rules")
    print(f"    Loop: {len(spec.loop)} steps")


def test_game_state_serialization():
    """测试游戏状态序列化/反序列化"""
    from core.state import GameState, TurnRecord
    
    state = GameState(turn=10, day=2, phase="CHAPTER1", player_location="教室")
    state.history.append(TurnRecord(turn=1, narrative="测试叙事", player_input="测试输入"))
    state.inventory.append("钥匙")
    state.add_flag("prologue_complete")
    
    data = state.to_dict()
    restored = GameState.from_dict(data)
    
    assert restored.turn == 10
    assert restored.day == 2
    assert restored.phase == "CHAPTER1"
    assert "钥匙" in restored.inventory
    assert restored.has_flag("prologue_complete")
    assert len(restored.history) == 1
    
    print(f"  ✓ GameState serialization: turn={restored.turn}, inv={restored.inventory}")


def test_safe_path_allowlist():
    """A3: safe_path 仅允许 skills_generated/ 与 skills/，并防前缀误判"""
    from web.security import allowed_roots, safe_path

    roots = allowed_roots()
    names = sorted(r.name for r in roots)
    assert names == ["skills", "skills_generated"], f"allowed_roots 异常: {names}"

    # 允许：两个根目录内的路径
    inside = roots[0] / "异界街角的店灵日志"
    assert safe_path(str(inside)) == inside.resolve()
    assert safe_path(str(roots[1] / "x")) == (roots[1] / "x").resolve()

    # 拒绝：根目录外
    outside = PROJECT_ROOT / "core"
    try:
        safe_path(str(outside))
        assert False, "应拒绝 skills/ 之外的路径"
    except ValueError:
        pass

    # 拒绝：前缀误判（skills_evil 不应被当作 skills 子目录）
    evil = PROJECT_ROOT / "skills_evil"
    try:
        safe_path(str(evil))
        assert False, "应拒绝 skills_evil 前缀误判"
    except ValueError:
        pass

    print(f"  ✓ safe_path: roots={names}, 前缀误判已防护")


def test_engine_tool_writeback():
    """A1/E1: 工具输出的 state_patch 并入顶层 custom，flags_to_set 并入 flags"""
    import tempfile
    import json
    from core.state import GameState
    from runtime.engine import GameEngine

    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td)
        (skill_dir / "tools").mkdir(parents=True, exist_ok=True)
        tool = skill_dir / "tools" / "echo.py"
        tool.write_text(
            "import json\n"
            "print(json.dumps({"
            "'state_patch': {'balance_copper': 347, 'prosperity': 27, 'day': 5},"
            "'flags_to_set': ['act1_exit_ready'],"
            "'narrative_hint': 'x'"
            "}, ensure_ascii=False))\n",
            encoding="utf-8",
        )

        eng = GameEngine.__new__(GameEngine)
        eng.skill_dir = skill_dir
        eng.state = GameState()
        eng._handle_tool({"tool": "echo.py"})

        # 普通字段 → 顶层 custom
        assert eng.state.custom.get("balance_copper") == 347
        assert eng.state.custom.get("prosperity") == 27
        # 白名单字段 → GameState 顶层属性，且不落入 custom
        assert eng.state.day == 5
        assert "day" not in eng.state.custom
        assert eng.state.has_flag("act1_exit_ready")
        assert isinstance(eng.state.custom.get("last_tool_result"), dict)
    print("  ✓ engine E1 writeback: custom patched + flag set")


def test_game_dianling_tools():
    """《异界街角的店灵日志》工具链契约（以子进程方式，模拟引擎调用）"""
    import subprocess
    import json
    game_dir = PROJECT_ROOT / "skills" / "异界街角的店灵日志"
    tools = game_dir / "tools"
    if not (tools / "time_block.py").exists():
        print("  - 跳过：游戏目录尚未生成")
        return

    def run(script, *args):
        r = subprocess.run([sys.executable, str(tools / script), *args],
                           cwd=str(game_dir), capture_output=True,
                           text=True, encoding="utf-8")
        assert r.returncode == 0, f"{script} 失败: {r.stderr}"
        return r

    # 1) 初始化（Prologue Part1: 现代世界）
    run("session_starter.py")
    save = json.loads((game_dir / "saves" / "autosave.json").read_text(encoding="utf-8"))
    assert save["phase"].startswith("PROLOGUE_PART"), save["phase"]
    sim = save["custom"]["last_tool_result"]["sim"]
    assert sim["balance"] == 600
    assert len(sim["menu"]) == 5
    assert set(sim["npcs"]) == {"ada", "line", "bardo"}

    # 1b) 验证 PROLOGUE_PART1 期间 time_block 不泄漏咖啡店数据
    out_p1 = json.loads(run("time_block.py").stdout)
    assert "state_patch" in out_p1
    if save["phase"] == "PROLOGUE_PART1":
        assert "余额" not in out_p1.get("state_patch", {})
        assert "繁荣度" not in out_p1.get("state_patch", {})

    # 手动将阶段推进到 PART3（咖啡店模拟完全上线后），测试后续工具链
    save["phase"] = "PROLOGUE_PART3"
    (game_dir / "saves" / "autosave.json").write_text(json.dumps(save, ensure_ascii=False),
                                                      encoding="utf-8")

    # 2) 调度器 — 推进进入营业并出餐
    out = json.loads(run("time_block.py", "开店营业").stdout)
    for k in ("sim", "state_patch", "flags_to_set"):
        assert k in out, f"缺少 {k}"
    assert "余额" in out["state_patch"] and "繁荣度" in out["state_patch"]
    assert out["state_patch"]["时间块"] == "午前营业"
    assert "block_result" in out

    # 3) 店灵能力意图匹配
    out = json.loads(run("time_block.py", "让艾达注意到窗台上的那封信").stdout)
    assert out.get("spirit_result", {}).get("ability") == "轻推"

    # 4) 快进多日 — 验证疲劳有界（跨夜恢复生效）
    out = json.loads(run("time_block.py", "快进20天").stdout)
    assert "fast_summary" in out
    fats = [n["fatigue"] for n in out["sim"]["npcs"].values()]
    assert max(fats) < 95, f"疲劳失控: {fats}"
    assert out["flags_to_set"], "快进多日后应至少置 prologue_complete"

    print(f"  ✓ 店灵日志工具链: 初始化/调度/能力/快进 OK, 疲劳上限={max(fats)}")


def test_game_dianling_engine():
    """端到端：用桩 LLM 启动 GameEngine 跑两回合，验证 引擎+调度器+E1+面板 串通。"""
    import json
    game_dir = PROJECT_ROOT / "skills" / "异界街角的店灵日志"
    if not (game_dir / "loop_schema.json").exists():
        print("  - 跳过：游戏目录尚未生成")
        return

    from runtime.engine import GameEngine

    class _Resp:
        content = "（测试叙事）"
        tool_calls = []

    class _StubLLM:
        def chat_agent(self, **kwargs):
            return _Resp()

        def close(self):
            pass

    # 删除存档强制全新初始化
    autosave = game_dir / "saves" / "autosave.json"
    if autosave.exists():
        autosave.unlink()

    engine = GameEngine(str(game_dir), _StubLLM())
    try:
        assert engine.state.phase.startswith("PROLOGUE_PART"), engine.state.phase

        gen = engine.run_loop()
        e1 = next(gen)
        assert e1["type"] == "narrative", e1
        # PROLOGUE_PART1: state.custom 不包含咖啡店字段
        assert "余额" not in engine.state.custom
        assert "繁荣度" not in engine.state.custom
        assert engine.state.day == 1

        e2 = next(gen)
        assert e2["type"] == "wait_input", e2

        # 发送输入触发 LLM → 进入下一轮，推进到 PART2
        e3 = gen.send("推进")
        assert e3["type"] == "narrative", e3

        # 消耗 PROLOGUE_PART2 的 pause（gen.send 仅消费一个 yield）
        eb = next(gen)
        assert eb["type"] == "wait_input"

        # 手动将阶段跳到 PART3，模拟完整的咖啡店模拟上线
        engine.phase_machine.set_phase("PROLOGUE_PART3")
        engine.state.phase = "PROLOGUE_PART3"
        engine.state.player_location = "咖啡店"

        e4 = gen.send("开店营业")
        assert e4["type"] == "narrative", e4
        # 推进意图被调度器消费 → 进入午前营业（E1 回写）
        assert engine.state.custom.get("时间块") == "午前营业", engine.state.custom.get("时间块")
        assert "余额" in engine.state.custom
        assert "繁荣度" in engine.state.custom
    finally:
        engine.shutdown()

    print("  ✓ GameEngine 端到端: 启动→叙事→输入→推进 OK")


if __name__ == "__main__":
    print("\n★ TRPG-to-SKILL — 集成测试\n")
    
    tests = [
        test_parser,
        test_lorebook_index,
        test_phase_machine,
        test_config_manager,
        test_compiler_dry_run,
        test_game_state_serialization,
        test_safe_path_allowlist,
        test_engine_tool_writeback,
        test_game_dianling_tools,
        test_game_dianling_engine,
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
    
    print(f"\n  结果: {passed}/{len(tests)} 通过\n")

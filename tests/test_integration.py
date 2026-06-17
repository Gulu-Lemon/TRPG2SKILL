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


if __name__ == "__main__":
    print("\n★ TRPG-to-SKILL — 集成测试\n")
    
    tests = [
        test_parser,
        test_lorebook_index,
        test_phase_machine,
        test_config_manager,
        test_compiler_dry_run,
        test_game_state_serialization,
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
    
    print(f"\n  结果: {passed}/{len(tests)} 通过\n")

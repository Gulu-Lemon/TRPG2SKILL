"""
游戏 Blueprint — 同步请求-响应模式（无 SSE 持久连接）
"""
import json
import queue
import threading
from pathlib import Path
from flask import Blueprint, request

play_bp = Blueprint("play", __name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

_engine = None
_engine_lock = threading.Lock()
_engine_gen = None      # 持久生成器引用


def _ensure_imports():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))


def _advance_once(gen):
    """推进生成器一次，返回事件 dict。处理异常。"""
    try:
        evt = next(gen)
        return evt
    except StopIteration:
        return {"type": "_done_"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"type": "error", "content": str(e)}


@play_bp.route("/load", methods=["POST"])
def load_game():
    global _engine, _engine_gen
    _ensure_imports()

    data = request.get_json()
    game_dir = data.get("game_dir", "")
    if not game_dir:
        return {"error": "缺少 game_dir"}, 400

    from core.config_profiles import create_llm_from_profile
    from runtime.engine import GameEngine
    from pathlib import Path as P

    gd = P(game_dir)
    if not gd.is_absolute():
        gd = PROJECT_ROOT / gd
    gd = gd.resolve()

    # 验证 SKILL 目录有效性
    if not gd.is_dir():
        return {"error": "目录不存在"}, 400
    schema_path = gd / "loop_schema.json"
    if not schema_path.exists():
        return {"error": "缺少 loop_schema.json，不可加载"}, 400
    try:
        import json as _json
        schema = _json.loads(schema_path.read_text(encoding="utf-8"))
        if not schema.get("loop"):
            return {"error": "loop_schema.json 中无游戏循环定义"}, 400
    except Exception as e:
        return {"error": f"loop_schema.json 读取失败: {e}"}, 400

    with _engine_lock:
        if _engine:
            try:
                _engine.shutdown()
            except Exception:
                pass
        try:
            llm = create_llm_from_profile()
            _engine = GameEngine(str(gd), llm)
        except Exception as e:
            return {"error": f"加载失败: {type(e).__name__}: {e}"}, 500
        _engine_gen = None

    return {"ok": True, "game_name": _engine.loop_schema.get("game_name", ""),
            "phase": _engine.state.phase, "turn": _engine.state.turn,
            "location": _engine.state.player_location,
            "history": [{"turn": r.turn, "narrative": r.narrative, "player_input": r.player_input}
                        for r in _engine.state.history[-20:]]}


@play_bp.route("/narrate", methods=["POST"])
def narrate():
    """生成当前轮叙事，返回 JSON"""
    global _engine, _engine_gen
    if not _engine:
        return {"error": "无活动游戏"}, 400

    if _engine_gen is None:
        _engine_gen = _engine.run_loop()

    # 推进到叙事 (经过 read_state, route, tool, 到达 llm_narrative)
    evt = _advance_once(_engine_gen)
    if evt['type'] == 'error':
        return {"error": evt.get('content', '叙事生成失败')}, 500
    if evt['type'] == '_done_':
        return {"error": "游戏已结束"}, 400

    narrative = evt.get('content', '')

    # 推进到 wait_input (经过 pause 步骤)
    evt = _advance_once(_engine_gen)
    waiting = evt['type'] == 'wait_input'

    s = _engine.state
    return {"narrative": narrative,
            "turn": s.turn, "day": s.day,
            "phase": s.phase, "location": s.player_location,
            "inventory": s.inventory[:10],
            "flags": s.flags[-10:],
            "custom": {k: v for k, v in s.custom.items()
                       if k not in ("routed_tool", "last_tool_result")},
            "waiting": waiting}


@play_bp.route("/input", methods=["POST"])
def player_input():
    """发送玩家输入，生成下一轮叙事，返回 JSON"""
    global _engine, _engine_gen
    if not _engine:
        return {"error": "无活动游戏"}, 400

    if _engine_gen is None:
        return {"error": "请先调用 /api/play/narrate 开始游戏"}, 400

    data = request.get_json()
    text = (data or {}).get("text", "").strip()
    if not text:
        return {"error": "输入为空"}, 400

    # 发送到生成器 → 推进到下一轮叙事
    try:
        result = _engine_gen.send(text)
    except StopIteration:
        _engine_gen = None
        return {"error": "游戏已结束"}, 400
    except Exception as e:
        return {"error": str(e)}, 500

    if isinstance(result, dict) and result['type'] == 'narrative':
        narrative = result.get('content', '')
    elif isinstance(result, dict) and result['type'] == 'error':
        return {"error": result.get('content', str(result))}, 500
    else:
        narrative = str(result)

    # 推进到 wait_input
    evt = _advance_once(_engine_gen)
    waiting = evt['type'] == 'wait_input'

    s = _engine.state
    return {"narrative": narrative,
            "turn": s.turn, "day": s.day,
            "phase": s.phase, "location": s.player_location,
            "inventory": s.inventory[:10],
            "flags": s.flags[-10:],
            "custom": {k: v for k, v in s.custom.items()
                       if k not in ("routed_tool", "last_tool_result")},
            "waiting": waiting}


@play_bp.route("/state", methods=["GET"])
def get_state():
    global _engine
    if not _engine:
        return {"error": "无活动游戏"}, 400
    s = _engine.state
    state_fields = _engine.loop_schema.get("state_fields", [])
    return {"turn": s.turn, "day": s.day, "phase": s.phase,
            "location": s.player_location, "inventory": s.inventory[:20],
            "flags": s.flags[-20:], "npcs": list(s.npcs.keys())[:10],
            "custom": {k: v for k, v in s.custom.items()
                       if k not in ("routed_tool", "last_tool_result")},
            "state_fields": state_fields}


@play_bp.route("/reset", methods=["POST"])
def reset_game():
    global _engine, _engine_gen
    if not _engine:
        return {"error": "无活动游戏"}, 400
    saves_dir = _engine.skill_dir / "saves"
    if saves_dir.exists():
        for f in saves_dir.glob("*.json"):
            f.unlink()
    from runtime.tool_runner import init_session
    try:
        init_session(_engine.skill_dir)
    except Exception:
        pass
    _engine._state_loaded = False
    _engine._load_or_init_state()
    _engine_gen = None
    return {"ok": True, "game_name": _engine.loop_schema.get("game_name", "")}


@play_bp.route("/command", methods=["POST"])
def send_command():
    global _engine
    if not _engine:
        return {"error": "无活动游戏"}, 400
    data = request.get_json()
    cmd = data.get("cmd", "")

    if cmd == "/hotreload":
        changed = _engine.hot_reload.poll(_engine.lorebook, _engine.config_mgr)
        if changed:
            _engine.config = _engine.config_mgr.data
            return {"ok": True, "changed": len(changed)}
        return {"ok": True, "changed": 0}

    return {"error": f"未知命令: {cmd}"}, 400


@play_bp.route("/list", methods=["GET"])
def list_skills():
    import json as _json
    skills = []
    seen = set()

    for base_dir in [PROJECT_ROOT / "generated", PROJECT_ROOT.parent / "SKILL打包区"]:
        if not base_dir.exists():
            continue
        for d in sorted(base_dir.iterdir()):
            if not d.is_dir():
                continue
            # 跳过名称异常长的目录（可能是路径拼接错误）
            if len(d.name) > 80 or any(c in d.name for c in '\\/:*?"<>|'):
                continue
            schema_path = d / "loop_schema.json"
            loadable = True
            if not schema_path.exists():
                schema_path = d / "skill" / "SKILL.md"
                if not schema_path.exists():
                    continue
                loadable = False
                try:
                    name = d.name
                except Exception:
                    name = d.name
            else:
                try:
                    data = _json.loads(schema_path.read_text(encoding="utf-8"))
                    name = data.get("game_name", d.name)
                except Exception:
                    name = d.name

            if name in seen:
                continue
            seen.add(name)

            info = {"name": name, "path": str(d.resolve()), "dir": d.name,
                     "loadable": loadable}
            save_path = d / "saves" / "autosave.json"
            if save_path.exists():
                try:
                    sd = _json.loads(save_path.read_text(encoding="utf-8"))
                    info["turn"] = sd.get("turn", 0)
                    info["phase"] = sd.get("phase", "")
                    info["saved"] = sd.get("updated_at", sd.get("created_at", ""))
                except Exception:
                    pass
            skills.append(info)

    return {"skills": skills}


@play_bp.route("/add", methods=["POST"])
def add_skill_dir():
    data = request.get_json()
    path_str = (data or {}).get("path", "").strip()
    if not path_str:
        return {"error": "路径为空"}, 400

    from pathlib import Path as P
    p = P(path_str)
    if not p.is_absolute():
        return {"error": "请使用绝对路径"}, 400
    if not p.is_dir():
        return {"error": "目录不存在"}, 400

    schema = p / "loop_schema.json"
    if not schema.exists():
        schema = p / "skill" / "SKILL.md"
        if not schema.exists():
            return {"error": "不是有效的 SKILL 目录（缺少 loop_schema.json）"}, 400

    return {"ok": True, "path": str(p.resolve())}


@play_bp.route("/scan", methods=["POST"])
def scan_dir():
    """扫描指定目录下的所有 SKILL 子目录"""
    data = request.get_json()
    path_str = (data or {}).get("dir", "").strip()
    if not path_str:
        return {"error": "路径为空"}, 400

    from pathlib import Path as P
    import json as _json
    p = P(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p = p.resolve()
    if not p.is_dir():
        return {"error": "目录不存在"}, 400

    skills = []
    for d in sorted(p.iterdir()):
        if not d.is_dir():
            continue
        if len(d.name) > 80 or any(c in d.name for c in '\\/:*?"<>|'):
            continue
        schema_path = d / "loop_schema.json"
        if not schema_path.exists():
            continue
        try:
            sd = _json.loads(schema_path.read_text(encoding="utf-8"))
            name = sd.get("game_name", d.name)
        except Exception:
            name = d.name

        info = {"name": name, "path": str(d.resolve()), "dir": d.name, "loadable": True}
        save_path = d / "saves" / "autosave.json"
        if save_path.exists():
            try:
                sv = _json.loads(save_path.read_text(encoding="utf-8"))
                info["turn"] = sv.get("turn", 0)
                info["phase"] = sv.get("phase", "")
                info["saved"] = sv.get("updated_at", sv.get("created_at", ""))
            except Exception:
                pass
        skills.append(info)

    return {"skills": skills, "scanned_path": str(p)}

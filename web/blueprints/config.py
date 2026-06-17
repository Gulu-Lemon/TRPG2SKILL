"""
配置 Blueprint — API 配置管理 + 游戏参数热重载
"""
import json
from pathlib import Path
from flask import Blueprint, request

config_bp = Blueprint("config", __name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent


# ── API 配置 CRUD ──

@config_bp.route("/profiles", methods=["GET"])
def profiles_get():
    import sys; sys.path.insert(0, str(PROJECT_ROOT))
    from core.config_profiles import list_profiles, get_active
    return {"profiles": list_profiles(), "active": get_active()}


@config_bp.route("/profiles", methods=["POST"])
def profiles_post():
    import sys; sys.path.insert(0, str(PROJECT_ROOT))
    from core.config_profiles import save_profile
    data = request.get_json()
    save_profile(**{k: v for k, v in data.items()
                    if k in ("name", "base_url", "api_key", "model",
                             "temperature", "top_p", "analyzer_model",
                             "thinking_mode", "thinking_budget")})
    return {"ok": True}


@config_bp.route("/profiles/activate", methods=["POST"])
def profiles_activate():
    import sys; sys.path.insert(0, str(PROJECT_ROOT))
    from core.config_profiles import activate, apply_to_llm
    from web.blueprints.play import _engine
    name = request.get_json()["name"]
    activate(name)
    if _engine:
        apply_to_llm(_engine.llm)
    return {"ok": True}


@config_bp.route("/profiles/delete", methods=["POST"])
def profiles_delete():
    import sys; sys.path.insert(0, str(PROJECT_ROOT))
    from core.config_profiles import delete_profile
    delete_profile(request.get_json()["name"])
    return {"ok": True}


@config_bp.route("/test", methods=["GET"])
def test_connection():
    import sys, time; sys.path.insert(0, str(PROJECT_ROOT))
    from core.config_profiles import create_llm_from_profile
    t0 = time.time()
    try:
        llm = create_llm_from_profile()
        r = llm.chat(
            messages=[{"role": "user", "content": "回复一个字"}],
            max_tokens=5,
            temperature=0,
        )
        elapsed = int((time.time() - t0) * 1000)
        return {"ok": True, "model": llm.model, "latency_ms": elapsed, "response": r[:20]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 游戏配置热重载 ──

@config_bp.route("/game", methods=["GET"])
def game_config_get():
    from web.blueprints.play import _engine
    if not _engine:
        return {"fields": [], "error": "无活动游戏"}, 400
    return {"fields": _engine.config_mgr.get_all_for_gui()}


@config_bp.route("/game/update", methods=["POST"])
def game_config_update():
    from web.blueprints.play import _engine
    if not _engine:
        return {"error": "无活动游戏"}, 400
    data = request.get_json()
    _engine.config_mgr.update(data["key"], data["value"])
    _engine.config = _engine.config_mgr.data
    return {"ok": True}


@config_bp.route("/game/reset", methods=["POST"])
def game_config_reset():
    from web.blueprints.play import _engine
    if _engine:
        _engine.config_mgr.reset_all()
        _engine.config = _engine.config_mgr.data
    return {"ok": True}


@config_bp.route("/shutdown", methods=["GET"])
def shutdown():
    """优雅关闭服务器: 保存状态, 关闭连接, 退出进程"""
    import os as _os
    from web.blueprints.play import _engine, _engine_lock
    with _engine_lock:
        if _engine:
            _engine.shutdown()
    _os._exit(0)

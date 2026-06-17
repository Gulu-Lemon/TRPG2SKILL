"""
存档 Blueprint — 列出/保存/读取/删除存档
"""
import json
import time
from pathlib import Path
from flask import Blueprint, request

save_bp = Blueprint("save", __name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _get_saves_dir():
    from web.blueprints.play import _engine
    if not _engine:
        return None
    return _engine.skill_dir / "saves"


@save_bp.route("/slots", methods=["GET"])
def list_slots():
    import pathlib
    saves_dir = _get_saves_dir()
    if not saves_dir or not saves_dir.exists():
        saves_dir = None
    # 支持直接查看指定目录的存档
    dir_param = request.args.get("dir", "")
    if dir_param:
        saves_dir = pathlib.Path(dir_param)
        if not saves_dir.exists():
            return {"slots": []}

    slots = []
    for f in sorted(saves_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            slots.append({
                "name": f.stem,
                "turn": data.get("turn", 0),
                "day": data.get("day", 1),
                "phase": data.get("phase", ""),
                "location": data.get("player_location", ""),
                "date": data.get("updated_at", data.get("created_at", "")),
                "is_auto": f.stem == "autosave",
            })
        except Exception:
            pass

    return {"slots": slots}


@save_bp.route("/manual", methods=["POST"])
def save_manual():
    saves_dir = _get_saves_dir()
    if not saves_dir:
        return {"error": "无活动游戏"}, 400

    name = (request.get_json() or {}).get("name", time.strftime("%Y%m%d_%H%M%S"))
    from web.blueprints.play import _engine
    _engine._write_state()

    autosave = saves_dir / "autosave.json"
    dest = saves_dir / f"slot_{name}.json"

    if autosave.exists():
        data = json.loads(autosave.read_text(encoding="utf-8"))
        data["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "name": name}

    return {"error": "无自动存档"}, 400


@save_bp.route("/load/<name>", methods=["POST"])
def load_save(name):
    saves_dir = _get_saves_dir()
    if not saves_dir:
        return {"error": "无活动游戏"}, 400

    src = saves_dir / f"{name}.json"
    if not src.exists():
        src = saves_dir / f"slot_{name}.json"
    if not src.exists():
        return {"error": "存档不存在"}, 404

    data = json.loads(src.read_text(encoding="utf-8"))
    autosave = saves_dir / "autosave.json"
    autosave.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 重新加载引擎状态
    from web.blueprints.play import _engine
    if _engine:
        from core.state import GameState
        _engine.state = GameState.from_dict(data)

    return {"ok": True, "turn": data.get("turn", 0), "phase": data.get("phase", ""),
            "location": data.get("player_location", ""),
            "history": data.get("history", [])[-20:]}


@save_bp.route("/<name>", methods=["DELETE"])
def delete_save(name):
    saves_dir = _get_saves_dir()
    if not saves_dir:
        return {"error": "无活动游戏"}, 400
    path = saves_dir / f"slot_{name}.json"
    if path.exists():
        path.unlink()
        return {"ok": True}
    return {"error": "存档不存在"}, 404

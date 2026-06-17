"""
Lorebook Blueprint — 查看激活的 Lorebook 条目
"""
import json
from pathlib import Path
from flask import Blueprint

lorebook_bp = Blueprint("lorebook", __name__)


@lorebook_bp.route("/entries", methods=["GET"])
def list_entries():
    from web.blueprints.play import _engine
    if not _engine:
        return {"entries": [], "error": "无活动游戏"}

    entries = []
    for e in _engine.lorebook.entries.values():
        entries.append({
            "id": e.id,
            "title": e.title,
            "content": e.content[:200],
            "type": e.type,
            "keys": e.keys,
            "strategy": e.strategy.value,
            "priority": e.priority,
        })

    return {"entries": sorted(entries, key=lambda e: -e["priority"])}


@lorebook_bp.route("/active", methods=["GET"])
def active_entries():
    from web.blueprints.play import _engine
    if not _engine:
        return {"entries": []}

    # 模拟一次 resolve 查看哪些会激活
    state = _engine.state
    messages = _engine.memory.build_messages(state)
    active = _engine.lorebook.resolve(
        messages, state,
        max_tokens=_engine.config.get("lorebook", {}).get("max_injection_tokens", 3000)
    )

    return {"entries": [
        {"id": e.id, "title": e.title, "type": e.type, "strategy": e.strategy.value,
         "priority": e.priority}
        for e in active
    ]}

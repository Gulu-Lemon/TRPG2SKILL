"""
编辑 Blueprint — 审核面板直接修改已编译的 SKILL 文件
"""
import json
import threading
from pathlib import Path
from flask import Blueprint, request

edit_bp = Blueprint("edit", __name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent
_edit_lock = threading.Lock()


def _read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── AGENTS.md 编辑 ──

@edit_bp.route("/bans", methods=["GET"])
def get_bans():
    """读取当前 AGENTS.md 的禁令列表"""
    data = request.args.get("dir", "")
    if not data:
        return {"error": "缺少 dir 参数"}, 400
    path = Path(data) / "AGENTS.md"
    if not path.exists():
        return {"bans": []}
    text = path.read_text(encoding="utf-8")
    bans = []
    for line in text.split("\n"):
        if line.startswith("### "):
            bans.append({"title": line[4:].strip(), "text": ""})
        elif line.startswith("> ") and bans:
            bans[-1]["text"] += line[2:] + "\n"
    for b in bans:
        b["text"] = b["text"].strip()
    # 过滤掉非禁令的行（"叙事风格"/"行动权隔离"等自动生成的）
    return {"bans": bans}


@edit_bp.route("/bans", methods=["POST"])
def update_bans():
    """更新 AGENTS.md — 支持删除、合并、重写"""
    data = request.get_json()
    dir_path = data.get("dir", "")
    bans = data.get("bans", [])
    if not dir_path:
        return {"error": "缺少 dir"}, 400

    path = Path(dir_path) / "AGENTS.md"
    lines = [f"# AGENTS.md — 核心规则\n", "\n",
             "每次游戏启动时自动读取。仅包含强制执行规则。\n", "\n",
             "---\n", "\n", "## 绝对禁令\n", "\n"]
    for b in bans:
        title = b.get("title", "").strip()
        text = b.get("text", "").strip()
        if not title and not text:
            continue
        lines.append(f"### {title}\n")
        for t in text.split("\n"):
            lines.append(f"> {t}\n")
        lines.append("\n")
    lines.append("---\n")
    lines.append("*由 TRPG2SKILL 审核面板编辑*\n")

    with _edit_lock:
        path.write_text("".join(lines), encoding="utf-8")
    return {"ok": True}


@edit_bp.route("/bans/smart-dedup", methods=["POST"])
def smart_dedup():
    """用 LLM 去重+合并 AGENTS.md 冗余禁令"""
    data = request.get_json()
    dir_path = data.get("dir", "")
    if not dir_path:
        return {"error": "缺少 dir"}, 400

    path = Path(dir_path) / "AGENTS.md"
    if not path.exists():
        return {"bans": []}

    text = path.read_text(encoding="utf-8")

    from core.config_profiles import create_llm_from_profile
    llm = create_llm_from_profile()

    try:
        result = llm.chat_json(
            messages=[{"role": "user", "content": text}],
            system="""你是 AGENTS.md 精简器。去重并合并以下禁令列表。

规则：
1. 意思相同或高度相似的禁令合并为一条，保留最完整/最精确的表述
2. 优先级从高到低：行动权隔离 > 全局用词规则 > 世界观设定 > 篇幅控制 > 其他
3. 每条禁令输出 title（简短概括）和 text（完整规则）
4. 合并后目标：3-7 条，不要超过 7 条
5. 禁止自己编造新的规则

输出 JSON: {"bans": [{"title": "...", "text": "..."}]}""",
            temperature=0.2, max_tokens=2000
        )
        return {"bans": result.get("bans", [])}
    except Exception as e:
        return {"error": str(e)}, 500


# ── Lorebook 编辑 ──

@edit_bp.route("/lorebook", methods=["GET"])
def get_lorebook():
    data = request.args.get("dir", "")
    if not data:
        return {"error": "缺少 dir"}, 400
    path = Path(data) / "lorebook.json"
    if not path.exists():
        return {"entries": []}
    d = _read_json(path)
    return {"entries": d.get("entries", [])}


@edit_bp.route("/lorebook", methods=["POST"])
def update_lorebook():
    """更新 lorebook.json 条目"""
    data = request.get_json()
    dir_path = data.get("dir", "")
    entries = data.get("entries", [])
    if not dir_path:
        return {"error": "缺少 dir"}, 400

    path = Path(dir_path) / "lorebook.json"
    d = _read_json(path)
    d["entries"] = entries
    with _edit_lock:
        _write_json(path, d)
    return {"ok": True}


# ── 工具数据池编辑 ──

@edit_bp.route("/tool-pool", methods=["GET"])
def get_tool_pool():
    dir_path = request.args.get("dir", "")
    tool_name = request.args.get("tool", "")
    if not dir_path or not tool_name:
        return {"error": "缺少参数"}, 400
    path = Path(dir_path) / "tools" / tool_name
    if not path.exists():
        return {"pool": []}
    text = path.read_text(encoding="utf-8")
    # 提取 POOL = [...] 中的数据
    import re, ast
    m = re.search(r'POOL\s*=\s*(\[[\s\S]*?\n\])', text)
    if m:
        try:
            pool = ast.literal_eval(m.group(1))
            return {"pool": pool}
        except Exception:
            pass
    return {"pool": []}


@edit_bp.route("/tool-pool", methods=["POST"])
def update_tool_pool():
    """更新工具的数据池（替换 POOL = [...] 部分）"""
    data = request.get_json()
    dir_path = data.get("dir", "")
    tool_name = data.get("tool", "")
    pool = data.get("pool", [])
    if not dir_path or not tool_name:
        return {"error": "缺少参数"}, 400

    path = Path(dir_path) / "tools" / tool_name
    if not path.exists():
        return {"error": "工具文件不存在"}, 404

    import re
    text = path.read_text(encoding="utf-8")
    pool_json = json.dumps(pool, ensure_ascii=False, indent=4)
    new_text = re.sub(
        r'POOL\s*=\s*\[[\s\S]*?\n\]',
        f'POOL = {pool_json}',
        text,
        count=1
    )
    with _edit_lock:
        path.write_text(new_text, encoding="utf-8")
    return {"ok": True}


# ── AGENTS.md 全文编辑（游戏内） ──

@edit_bp.route("/agents", methods=["GET"])
def get_agents():
    data = request.args.get("dir", "")
    if not data:
        return {"error": "缺少 dir"}, 400
    path = Path(data) / "AGENTS.md"
    if not path.exists():
        return {"text": ""}
    return {"text": path.read_text(encoding="utf-8")}


@edit_bp.route("/agents", methods=["POST"])
def update_agents():
    data = request.get_json()
    dir_path = data.get("dir", "")
    text = data.get("text", "")
    if not dir_path:
        return {"error": "缺少 dir"}, 400
    path = Path(dir_path) / "AGENTS.md"
    with _edit_lock:
        path.write_text(text, encoding="utf-8")
    return {"ok": True}

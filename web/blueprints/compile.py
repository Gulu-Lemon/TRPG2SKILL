"""
编译 Blueprint — SSE 流式编译进度（多阶段管线）
"""
import json
import queue
import threading
from pathlib import Path
from flask import Blueprint, Response, request, stream_with_context

compile_bp = Blueprint("compile", __name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _clean_name(name: str) -> str:
    import re
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip().rstrip('.')
    if len(name) > 60:
        name = name[:60]
    if not name:
        name = "my_game"
    return name


@compile_bp.route("/start", methods=["POST"])
def compile_start():
    data = request.get_json()
    text = data.get("world_book_text", "")
    output_name = _clean_name(data.get("output_name", "my_game"))
    feedback = data.get("feedback", "")

    if not text.strip():
        return {"error": "世界书内容为空"}, 400

    def generate():
        q = queue.Queue()

        def progress_callback(phase, progress, detail):
            q.put({"type": phase + "_progress", "phase": phase,
                   "progress": progress, "detail": str(detail)})

        def worker():
            try:
                import sys
                sys.path.insert(0, str(PROJECT_ROOT))

                output_dir = PROJECT_ROOT / "generated" / output_name
                output_dir.mkdir(parents=True, exist_ok=True)

                tmp_file = output_dir / "_input.txt"
                tmp_file.write_text(text, encoding="utf-8")

                from compiler.pipeline import compile
                compile(str(tmp_file), str(output_dir), feedback=feedback,
                        progress_callback=progress_callback)

                tmp_file.unlink(missing_ok=True)
                q.put({"type": "ok", "output_dir": str(output_dir)})
            except Exception as e:
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put({"type": "_done_"})

        threading.Thread(target=worker, daemon=True).start()

        while True:
            try:
                evt = q.get(timeout=600)
            except queue.Empty:
                yield f"event: error\ndata: {json.dumps({'message':'编译超时'})}\n\n"
                break

            t = evt.pop("type", "message")
            if t == "_done_":
                break
            yield f"event: {t}\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@compile_bp.route("/phase", methods=["POST"])
def compile_phase():
    """选择性重编译单个 Phase"""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    data = request.get_json()
    text = data.get("world_book_text", "")
    output_name = _clean_name(data.get("output_name", "my_game"))
    phase_id = data.get("phase_id", 0)

    if not text.strip():
        return {"error": "世界书内容为空"}, 400

    from core.config_profiles import create_llm_from_profile
    from compiler.multi_analyzer import (
        ENTITY_PROMPT, RULES_PROMPT, STRUCTURE_PROMPT, TOOLS_PROMPT, merge_results
    )

    llm = create_llm_from_profile(use_analyzer=True)
    output_dir = PROJECT_ROOT / "generated" / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    def call_llm(system_prompt, max_tokens=2000):
        try:
            return llm.chat_json(
                messages=[{"role": "user", "content": text}],
                system=system_prompt, temperature=0.3, max_tokens=max_tokens,
            )
        except Exception as e:
            return {}

    # 读取已有结果
    entity, rules, structure, tools = {}, {}, {}, {}
    for fn, var in [("loop_schema.json", None)]:
        pass

    try:
        import json as _json
        ls = _json.loads((output_dir / "loop_schema.json").read_text(encoding="utf-8"))
    except Exception:
        ls = {}

    # 只重跑指定 Phase
    if phase_id == 1:
        entity = call_llm(ENTITY_PROMPT, max_tokens=3000)
    elif phase_id == 2:
        rules = call_llm(RULES_PROMPT, max_tokens=1500)
    elif phase_id == 3:
        structure = call_llm(STRUCTURE_PROMPT, max_tokens=1000)
    elif phase_id == 4:
        tools = call_llm(TOOLS_PROMPT, max_tokens=2000)
    else:
        return {"error": "无效的 phase_id"}, 400

    # 合并（用已有数据填充缺失 Phase）
    if phase_id != 1:
        for fn in (output_dir / "skill").glob("*.md"):
            entity.setdefault("section_texts", []).append({"title": fn.stem, "text": fn.read_text(encoding="utf-8")[:500]})

    analysis = merge_results(entity, rules, structure, tools)
    from compiler.mapper import map_to_spec
    from compiler.generator import generate
    spec = map_to_spec(analysis)
    generate(spec, output_dir)

    llm.close()
    return {"ok": True, "output_dir": str(output_dir), "phase_id": phase_id}

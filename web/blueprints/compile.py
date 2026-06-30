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
        _review_data = {}

        def progress_callback(phase, progress, detail, **extra):
            nonlocal _review_data
            if "review" in extra:
                _review_data = extra["review"]
            q.put({"type": phase + "_progress", "phase": phase,
                   "progress": progress, "detail": str(detail)})

        def worker():
            try:
                import sys
                sys.path.insert(0, str(PROJECT_ROOT))

                output_dir = PROJECT_ROOT / "skills_generated" / output_name
                output_dir.mkdir(parents=True, exist_ok=True)

                tmp_file = output_dir / "_input.txt"
                tmp_file.write_text(text, encoding="utf-8")

                from compiler.pipeline import compile
                compile(str(tmp_file), str(output_dir), feedback=feedback,
                        progress_callback=progress_callback)

                tmp_file.unlink(missing_ok=True)
                q.put({"type": "ok", "output_dir": str(output_dir),
                       "review": _review_data})
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



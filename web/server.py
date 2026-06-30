"""
TRPG-to-SKILL Web GUI — Flask 入口
"""
import atexit
import os
import sys
import signal
import threading
from pathlib import Path

_BASE = Path(__file__).resolve().parent

_running_app = None
_shutdown_done = False


def _cleanup():
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True

    def _do_cleanup():
        print("\n  Shutting down...", flush=True)
        try:
            from web.blueprints.play import _engine, _engine_lock
            acquired = _engine_lock.acquire(timeout=2)
            try:
                if _engine:
                    _engine.shutdown()
                    print("  Game state saved.", flush=True)
            finally:
                if acquired:
                    _engine_lock.release()
        except Exception as e:
            print(f"  Warning: {e}", flush=True)

    t = threading.Thread(target=_do_cleanup, daemon=True)
    t.start()
    t.join(timeout=5)
    os._exit(0)


def create_app():
    from flask import Flask, send_from_directory

    app = Flask(__name__,
                static_folder=str(_BASE / "static"),
                static_url_path="/_none_")

    # static files at root
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(app.static_folder, filename)

    from web.blueprints.compile import compile_bp
    from web.blueprints.play import play_bp
    from web.blueprints.config import config_bp
    from web.blueprints.save import save_bp
    from web.blueprints.lorebook import lorebook_bp
    from web.blueprints.edit import edit_bp

    app.register_blueprint(compile_bp, url_prefix="/api/compile")
    app.register_blueprint(play_bp, url_prefix="/api/play")
    app.register_blueprint(config_bp, url_prefix="/api/config")
    app.register_blueprint(save_bp, url_prefix="/api/save")
    app.register_blueprint(lorebook_bp, url_prefix="/api/lorebook")
    app.register_blueprint(edit_bp, url_prefix="/api/edit")

    return app


def main():
    global _running_app

    sys.path.insert(0, str(_BASE.parent))
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    atexit.register(_cleanup)

    _running_app = create_app()

    (_BASE.parent / "skills_generated").mkdir(parents=True, exist_ok=True)
    (_BASE.parent / "skills").mkdir(parents=True, exist_ok=True)

    print("\n  == TRPG-to-SKILL Web GUI ==")
    print("  -> http://127.0.0.1:8641")
    print("  Press Ctrl+C to stop\n")

    try:
        _running_app.run(host="127.0.0.1", port=8641, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("", flush=True)
    finally:
        _cleanup()
    sys.exit(0)


if __name__ == "__main__":
    main()

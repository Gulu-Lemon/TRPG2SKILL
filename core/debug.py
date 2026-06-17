"""
Debug 模块 — 环形缓冲日志。
从 Astral 项目复用，路径适配。Flask 相关功能仅 Web 模式激活。
"""
from __future__ import annotations
import os
import sys
import time
import json
import threading
import traceback
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)

LOG_DIR = os.path.join(_BASE, "logs")


def _ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


class RingBuffer:
    """固定容量的环形缓冲，避免日志文件无限增长"""

    def __init__(self, path: str, max_lines: int = 5000):
        self.path = path
        self.max_lines = max_lines

    def write(self, line: str):
        _ensure_dir()
        lines = []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                lines = []
        lines.append(line)
        if len(lines) > self.max_lines:
            lines = lines[-self.max_lines:]
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)


class AgentLogger:
    """游戏运行时日志 — 叙事/工具调用/错误"""

    def __init__(self, log_file: str = "runtime.log"):
        self.log = RingBuffer(os.path.join(LOG_DIR, log_file))
        self._lock = threading.Lock()

    def info(self, msg: str):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"
        with self._lock:
            self.log.write(line)

    def error(self, msg: str, exc: Exception = None):
        if exc:
            msg += f" | {type(exc).__name__}: {exc}"
        line = f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {msg}\n"
        with self._lock:
            self.log.write(line)

    def turn(self, turn_num: int, phase: str):
        line = f"\n{'=' * 40}\n[TURN {turn_num}] phase={phase} "
        line += f"at {datetime.now().strftime('%H:%M:%S')}\n"
        with self._lock:
            self.log.write(line)

    def llm_call(self, purpose: str, tokens_in: int, tokens_out: int, duration_ms: int):
        line = f"  [LLM] {purpose} | {tokens_in}→{tokens_out} tokens | {duration_ms}ms\n"
        with self._lock:
            self.log.write(line)

    def tool_call(self, tool_name: str, success: bool, output_preview: str = ""):
        status = "OK" if success else "FAIL"
        preview = output_preview[:80].replace('\n', ' ') if output_preview else ""
        line = f"  [TOOL] {tool_name} → {status} | {preview}\n"
        with self._lock:
            self.log.write(line)

    def lorebook(self, hits: int, entries: list[str]):
        names = ", ".join(entries[:5])
        if len(entries) > 5:
            names += f" (+{len(entries) - 5})"
        line = f"  [LOREBOOK] {hits} hits → activated: {names}\n"
        with self._lock:
            self.log.write(line)


# ====== Flask 功能（仅 Web 模式使用）======

def install_flask(app):
    """安装 Flask 日志中间件。仅在 Web 模式调用。"""
    RequestLogger(app)
    ExceptionCatcher(app)
    print(f"  [Debug] 日志目录: {LOG_DIR}")
    return AgentLogger()


class RequestLogger:
    """Flask HTTP 请求日志"""

    def __init__(self, app, log_file: str = "requests.log"):
        self.log = RingBuffer(os.path.join(LOG_DIR, log_file))
        app.before_request(self._before)
        app.after_request(self._after)

    def _before(self):
        from flask import request, g
        g._req_start = time.time()
        g._req_id = datetime.now().strftime("%H%M%S") + str(int(time.time() * 1000) % 1000)

    def _after(self, response):
        from flask import request, g
        elapsed = (time.time() - getattr(g, "_req_start", time.time())) * 1000
        rid = getattr(g, "_req_id", "????")
        body = ""
        if request.is_json and request.get_data():
            raw = request.get_data(as_text=True)[:200]
            body = f" body={raw}"
        line = f"[{rid}] {request.method} {request.path} -> {response.status_code} ({elapsed:.0f}ms){body}\n"
        self.log.write(line)
        return response


class ExceptionCatcher:
    """全局异常捕获"""

    def __init__(self, app, log_file: str = "errors.log"):
        self.log = RingBuffer(os.path.join(LOG_DIR, log_file))
        app.register_error_handler(Exception, self._handler)
        self._install_thread_hook()

    def _handler(self, exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        tb = traceback.format_exc()
        stamp = datetime.now().isoformat()
        entry = f"\n{'=' * 60}\n[{stamp}] UNCAUGHT EXCEPTION\n{tb}\n{'=' * 60}\n"
        self.log.write(entry)
        print(f"\n[ERROR] {exc}\n{tb[:300]}", file=sys.stderr, flush=True)
        return {"ok": False, "error": str(exc), "trace": tb[:500]}, 500

    def _install_thread_hook(self):
        original = threading.Thread._bootstrap_inner

        def patched_bootstrap_inner(self_):
            try:
                original(self_)
            except Exception as exc:
                tb = traceback.format_exc()
                stamp = datetime.now().isoformat()
                entry = f"\n{'=' * 60}\n[{stamp}] THREAD EXCEPTION (thread={self_.name})\n{tb}\n{'=' * 60}\n"
                log = RingBuffer(os.path.join(LOG_DIR, "thread_errors.log"))
                log.write(entry)
                print(f"\n[THREAD ERROR] {self_.name}: {exc}\n{tb[:300]}", file=sys.stderr, flush=True)
                raise

        threading.Thread._bootstrap_inner = patched_bootstrap_inner

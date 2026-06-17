"""
工具执行器 — 安全调用生成目录中的 Python 工具脚本
"""
from pathlib import Path
import subprocess
import sys
import json
from typing import Any


class ToolExecutionError(Exception):
    def __init__(self, tool_name: str, stderr: str):
        self.tool_name = tool_name
        self.stderr = stderr
        super().__init__(f"工具 {tool_name} 执行失败: {stderr[:200]}")


def run_tool(skill_dir: Path, tool_name: str, args: list[str] = None,
             timeout: int = 10) -> Any:
    """
    执行生成目录中的 Python 工具脚本。
    
    Args:
        skill_dir: SKILL 目录根路径
        tool_name: 工具脚本文件名 (如 "npc_roller.py")
        args: 命令行参数列表
        timeout: 超时秒数
    
    Returns:
        JSON 解析结果（dict/list），或原始文本（无法解析 JSON 时）
    """
    tool_path = skill_dir / "tools" / tool_name
    if not tool_path.exists():
        raise ToolExecutionError(tool_name, f"文件不存在: {tool_path}")

    cmd = [sys.executable, str(tool_path)] + (args or [])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding="utf-8",
            timeout=timeout,
            cwd=str(skill_dir),
        )
    except subprocess.TimeoutExpired:
        raise ToolExecutionError(tool_name, f"超时 ({timeout}s)")
    
    if result.returncode != 0:
        raise ToolExecutionError(tool_name, (result.stderr or result.stdout or ""))

    output = (result.stdout or "").strip()
    if not output:
        return None

    # 尝试解析 JSON
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def init_session(skill_dir: Path) -> dict:
    """运行 session_starter.py 初始化新游戏"""
    return run_tool(skill_dir, "session_starter.py")

"""
路径安全中间件 — 防御路径遍历攻击
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def allowed_roots() -> list[Path]:
    """SKILL 可加载/扫描的根目录：编译产物 + 手动添加的成品。"""
    return [
        (PROJECT_ROOT / "skills_generated").resolve(),
        (PROJECT_ROOT / "skills").resolve(),
    ]


def safe_path(user_path: str) -> Path:
    """校验并返回安全的绝对路径，拒绝路径遍历攻击。

    仅允许位于 skills_generated/ 或 skills/ 之内（含其本身）的路径。
    使用 Path.is_relative_to 避免 startswith 前缀误判（如 skills_evil）。
    """
    p = Path(user_path).resolve()
    for root in allowed_roots():
        if p == root or p.is_relative_to(root):
            return p
    raise ValueError(f"路径不在允许范围内: {p}")

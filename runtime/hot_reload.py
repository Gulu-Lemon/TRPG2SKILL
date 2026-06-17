"""
热重载监控器 — 文件变更检测 + 自动刷新子系统
"""
from pathlib import Path
import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.lorebook import LorebookManager
    from core.config_schema import ConfigManager


class HotReloadWatcher:
    """
    监控 SKILL 目录中的关键文件，检测变更后在下一轮自动生效。
    
    监控范围:
    - AGENTS.md       → 重新加载到引擎内存
    - lorebook.json   → 重建 Lorebook 索引
    - game_config.json → 刷新所有子系统配置
    - skill/*.md       → 重新推导关键词 → 合并到 Lorebook
    """

    def __init__(self, skill_dir: Path):
        self.dir = skill_dir
        self.hashes: dict[str, str] = {}
        self._scan()

    def _scan(self):
        for ext in ("*.md", "*.json"):
            for f in self.dir.rglob(ext):
                # 排除存档和日志
                if "saves" in f.parts or "logs" in f.parts:
                    continue
                self.hashes[str(f)] = self._hash(f)

    def _hash(self, filepath: Path) -> str:
        if not filepath.exists():
            return ""
        return hashlib.md5(filepath.read_bytes()).hexdigest()

    def poll(self, lorebook: "LorebookManager" = None,
             config_mgr: "ConfigManager" = None) -> list[str]:
        """
        检查文件变更，自动触发子系统的重新加载。
        
        Returns:
            变更的文件名列表
        """
        changed = []

        # 检查已知文件
        for path_str, old_hash in list(self.hashes.items()):
            path = Path(path_str)
            if not path.exists():
                continue
            new_hash = self._hash(path)
            if new_hash != old_hash:
                changed.append(path_str)
                self.hashes[path_str] = new_hash

        # 检查新增文件
        for ext in ("*.md", "*.json"):
            for f in self.dir.rglob(ext):
                if "saves" in f.parts or "logs" in f.parts:
                    continue
                path_str = str(f)
                if path_str not in self.hashes:
                    changed.append(path_str)
                    self.hashes[path_str] = self._hash(f)

        if not changed:
            return []

        # 触发重新加载
        for path_str in changed:
            name = Path(path_str).name
            
            if name == "lorebook.json" and lorebook:
                lorebook.load()
                return changed
            
            if name == "game_config.json" and config_mgr:
                config_mgr.reload()
                return changed
            
            if name == "AGENTS.md":
                # 标记需要重新加载（由引擎处理）
                pass

        return changed

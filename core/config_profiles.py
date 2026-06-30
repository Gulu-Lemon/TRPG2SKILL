"""
API 配置管理 — config_profiles.json 多配置支持
从 Astral 项目复用，路径适配。
"""
import json
import os
import sys
import base64
from typing import Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)

PROFILES_PATH = os.path.join(_BASE, "config_profiles.json")


def _encode_key(key: str) -> str:
    if not key:
        return ""
    return base64.b64encode(key.encode()).decode()

def _decode_key(encoded: str) -> str:
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return encoded


def _ensure():
    if not os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump({"profiles": [], "active": ""}, f, indent=2, ensure_ascii=False)


def get_active() -> dict:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_name = data.get("active", "")
    for p in data.get("profiles", []):
        if p.get("name") == active_name:
            return {
                "name": p["name"].strip(),
                "base_url": p.get("base_url", "").strip(),
                "api_key": _decode_key(p.get("api_key", "").strip()),
                "model": p.get("model", "").strip(),
                "temperature": p.get("temperature", 1.0),
                "top_p": p.get("top_p", 0.95),
                "analyzer_model": p.get("analyzer_model", "").strip(),
                "thinking_mode": p.get("thinking_mode", False),
                "thinking_budget": p.get("thinking_budget", 0),
            }
    return {}


def list_profiles() -> list[dict]:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_name = data.get("active", "")
    profiles = []
    for p in data.get("profiles", []):
        entry = {
            "name": p.get("name", "").strip(),
            "base_url": p.get("base_url", "").strip(),
            "model": p.get("model", "").strip(),
            "temperature": p.get("temperature", 1.0),
            "top_p": p.get("top_p", 0.95),
            "analyzer_model": p.get("analyzer_model", "").strip(),
            "thinking_mode": p.get("thinking_mode", False),
            "thinking_budget": p.get("thinking_budget", 0),
        }
        entry["has_key"] = bool(p.get("api_key", "").strip())
        entry["active"] = p.get("name") == active_name
        profiles.append(entry)
    return profiles


def save_profile(name: str, base_url: str, api_key: str, model: str,
                 temperature: float = 1.0, top_p: float = 0.95,
                 analyzer_model: str = "",
                 thinking_mode: bool = False, thinking_budget: int = 0) -> bool:
    name = name.strip()
    base_url = base_url.strip()
    api_key = _encode_key(api_key.strip())
    model = model.strip() or "gpt-3.5-turbo"
    analyzer_model = analyzer_model.strip()
    try: temperature = float(temperature)
    except (ValueError, TypeError): temperature = 1.0
    try: top_p = float(top_p)
    except (ValueError, TypeError): top_p = 0.95
    try: thinking_budget = int(thinking_budget)
    except (ValueError, TypeError): thinking_budget = 0

    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    profiles = data.get("profiles", [])
    for i, p in enumerate(profiles):
        if p.get("name") == name:
            old_key = p.get("api_key", "")
            profiles[i] = {
                "name": name, "base_url": base_url,
                "api_key": api_key if api_key else old_key,
                "model": model,
                "temperature": temperature,
                "top_p": top_p,
                "analyzer_model": analyzer_model,
                "thinking_mode": thinking_mode,
                "thinking_budget": thinking_budget,
            }
            break
    else:
        profiles.append({
            "name": name, "base_url": base_url, "api_key": api_key, "model": model,
            "temperature": temperature, "top_p": top_p,
            "analyzer_model": analyzer_model,
            "thinking_mode": thinking_mode, "thinking_budget": thinking_budget,
        })
    if not data.get("active"):
        data["active"] = name
    data["profiles"] = profiles
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def activate(name: str) -> bool:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for p in data.get("profiles", []):
        if p.get("name") == name:
            data["active"] = name
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
    return False


def delete_profile(name: str) -> bool:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["profiles"] = [p for p in data.get("profiles", []) if p.get("name") != name]
    if data.get("active") == name:
        data["active"] = data["profiles"][0]["name"] if data["profiles"] else ""
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def apply_to_llm(llm) -> bool:
    cfg = get_active()
    if not cfg:
        return False
    llm.base_url = cfg["base_url"].rstrip("/")
    llm.api_key = cfg["api_key"]
    llm.model = cfg["model"]
    llm.default_temperature = cfg.get("temperature", 1.0)
    llm.default_top_p = cfg.get("top_p", 0.95)
    llm.thinking_enabled = cfg.get("thinking_mode", False)
    llm.thinking_budget = cfg.get("thinking_budget", 0)
    llm.close()
    return True


def create_llm_from_profile(use_analyzer: bool = False) -> "LLMClient":
    """从 active profile 创建 LLMClient，便捷工厂函数"""
    from .llm import LLMClient
    from .errors import ConfigError
    cfg = get_active()
    if not cfg:
        raise ConfigError("没有激活的 API 配置。请先运行设置。")
    client = LLMClient.from_dict(cfg)
    if use_analyzer and cfg.get("analyzer_model", "").strip():
        client.model = cfg["analyzer_model"].strip()
    return client

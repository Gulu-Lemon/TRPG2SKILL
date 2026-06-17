"""
LLM 客户端 — OpenAI 兼容 API（线程安全 · Agent 工具调用支持）
"""
from __future__ import annotations
import json
import os
import re
import threading
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class AgentResponse:
    """LLM Agent 响应，可能包含工具调用"""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = "stop"


class LLMClient:
    """线程安全的 OpenAI 兼容 API 客户端。
    
    支持三种构造方式:
    1. LLMClient(config_path="config.json") — 从文件加载
    2. LLMClient.from_dict(cfg) — 从 dict 加载（配合 config_profiles 使用）
    3. LLMClient() 然后手动设置属性
    """

    def __init__(self, config_path: str = ""):
        self._config_path = config_path
        self.default_temperature: float = 1.0
        self.default_top_p: float = 0.95
        self.base_url: str = ""
        self.api_key: str = ""
        self.model: str = ""
        self.thinking_enabled: bool = False
        self.thinking_budget: int = 0
        if config_path and os.path.exists(config_path):
            self.reload_config(config_path)
        self._local = threading.local()

    @classmethod
    def from_dict(cls, cfg: dict) -> "LLMClient":
        """从配置 dict 创建（配合 config_profiles.get_active()）"""
        client = cls()
        client.base_url = cfg.get("base_url", "").rstrip("/")
        client.api_key = cfg.get("api_key", "")
        client.model = cfg.get("model", "")
        client.default_temperature = cfg.get("temperature", 1.0)
        client.default_top_p = cfg.get("top_p", 0.95)
        client.thinking_enabled = cfg.get("thinking_mode", False)
        client.thinking_budget = cfg.get("thinking_budget", 0)
        return client

    def _get_client(self):
        import httpx
        if not hasattr(self._local, "client") or self._local.client is None:
            self._local.client = httpx.Client(timeout=120.0)
        return self._local.client

    def chat(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        if not self.api_key or not self.api_key.strip():
            raise ValueError("API Key 未配置。请在设置中添加并选择一个 API 配置。")
        if not self.base_url or not self.base_url.strip():
            raise ValueError("API 地址未配置。请在设置中添加并选择一个 API 配置。")
        if not self.model or not self.model.strip():
            raise ValueError("模型名未配置。请在设置中添加并选择一个 API 配置。")

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "top_p": top_p if top_p is not None else self.default_top_p,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload["thinking"] = {"type": "enabled"} if self.thinking_enabled else {"type": "disabled"}
        if self.thinking_enabled and self.thinking_budget > 0:
            payload["thinking"]["budget_tokens"] = self.thinking_budget
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            if not resp.text or not resp.text.strip():
                raise ValueError("API 返回了空响应")
            data = resp.json()
        except Exception as e:
            msg = f"API 调用失败。URL: {self.base_url}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f"，HTTP {e.response.status_code}: {e.response.text[:200]}"
            elif str(e).strip():
                msg += f"，错误: {str(e)[:200]}"
            raise ValueError(msg) from e
        return data["choices"][0]["message"]["content"].strip()

    def chat_agent(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: list[dict] = None,
    ) -> AgentResponse:
        """带工具调用的 Agent 对话，返回结构化响应"""
        if not self.api_key or not self.api_key.strip():
            raise ValueError("API Key 未配置")
        if not self.base_url or not self.base_url.strip():
            raise ValueError("API 地址未配置")
        if not self.model or not self.model.strip():
            raise ValueError("模型名未配置")

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        payload["thinking"] = {"type": "enabled"} if self.thinking_enabled else {"type": "disabled"}
        if self.thinking_enabled and self.thinking_budget > 0:
            payload["thinking"]["budget_tokens"] = self.thinking_budget

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            if not resp.text or not resp.text.strip():
                raise ValueError("API 返回了空响应")
            data = resp.json()
        except Exception as e:
            msg = f"API 调用失败。URL: {self.base_url}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f"，HTTP {e.response.status_code}: {e.response.text[:200]}"
            elif str(e).strip():
                msg += f"，错误: {str(e)[:200]}"
            raise ValueError(msg) from e

        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""

        # 解析 tool_calls
        tool_calls = []
        raw_calls = msg.get("tool_calls", [])
        for tc in raw_calls:
            func = tc.get("function", {})
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": args,
            })

        return AgentResponse(
            content=content.strip(),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        if not self.api_key or not self.api_key.strip():
            raise ValueError("API Key 未配置。")
        if not self.base_url or not self.base_url.strip():
            raise ValueError("API 地址未配置。")
        if not self.model or not self.model.strip():
            raise ValueError("模型名未配置。")

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload["thinking"] = {"type": "enabled"} if self.thinking_enabled else {"type": "disabled"}
        if self.thinking_enabled and self.thinking_budget > 0:
            payload["thinking"]["budget_tokens"] = self.thinking_budget
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
        except Exception as e:
            msg = f"流式 API 调用失败。URL: {self.base_url}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f"，HTTP {e.response.status_code}: {e.response.text[:200]}"
            elif str(e).strip():
                msg += f"，错误: {str(e)[:200]}"
            raise ValueError(msg) from e

    def chat_json(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 2048,
    ) -> dict:
        json_instruction = (
            "\n\n重要：你必须只输出一个有效的 JSON 对象，"
            "不要带任何 markdown 标记、解释、额外文字、或前后缀。直接输出 JSON。"
        )
        effective_system = (system or "") + json_instruction
        text = self.chat(
            messages, system=effective_system,
            temperature=temperature, max_tokens=max_tokens
        )
        return self._extract_json(text.strip())

    @staticmethod
    def _extract_json(raw: str) -> dict:
        text = raw
        code_block = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if code_block:
            text = code_block.group(1).strip()

        first = text.find('{')
        last = text.rfind('}')
        if first != -1 and last > first:
            text = text[first:last + 1]

        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        try:
            import ast
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            pass

        try:
            fixed = text.replace("'", '"')
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        try:
            full = raw
            code_block2 = re.search(r'```(?:json)?\s*\n?(.*?)```', full, re.DOTALL)
            if code_block2:
                full = code_block2.group(1).strip()
            first2 = full.find('{')
            if first2 != -1:
                full = full[first2:]
            brace_diff = full.count('{') - full.count('}')
            bracket_diff = full.count('[') - full.count(']')
            in_string = False
            escaped = False
            for ch in full:
                if escaped: escaped = False; continue
                if ch == '\\': escaped = True; continue
                if ch == '"': in_string = not in_string
            fixed = full
            if in_string:
                fixed += '"'
            inner = max(0, brace_diff - 1)
            fixed += '}' * inner
            fixed += ']' * bracket_diff
            if brace_diff > 0:
                fixed += '}'
            return json.loads(fixed)
        except (json.JSONDecodeError, Exception):
            pass

        raise ValueError(f"LLM 返回了空响应或非 JSON 内容: {raw[:200]}")

    def close(self):
        if hasattr(self._local, "client") and self._local.client is not None:
            self._local.client.close()
            self._local.client = None

    def set_model(self, model_name: str):
        self.model = model_name.strip()

    def reload_config(self, config_path: str = ""):
        path = config_path or self._config_path or "config.json"
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.base_url = cfg.get("base_url", cfg.get("api_base_url", "")).rstrip("/")
        self.api_key = cfg["api_key"]
        self.model = cfg.get("model", cfg.get("model_name", ""))
        self._config_path = path
        self.close()

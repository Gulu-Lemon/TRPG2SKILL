"""
游戏引擎 — 运行时主循环

读取 SKILL 目录。静态 system prompt + 动态上下文 user message，
实现 DeepSeek 前缀缓存命中。
"""
from __future__ import annotations
from pathlib import Path
import json
import time
from typing import Generator, Any

from core.state import GameState, TurnRecord, PhaseSpec
from core.llm import LLMClient
from core.config_schema import ConfigManager

_FALLBACK_LOOP = [
    {"step": 1, "type": "read_state"},
    {"step": 2, "type": "route"},
    {"step": 3, "type": "tool", "tool": "{routed_tool}"},
    {"step": 4, "type": "llm_narrative"},
    {"step": 5, "type": "pause"},
    {"step": 6, "type": "llm_process"},
    {"step": 7, "type": "write_state"},
]

from runtime.lorebook import LorebookManager
from runtime.prompt_assembler import PromptAssembler
from runtime.context_packer import pack_context
from runtime.phase_machine import PhaseMachine
from runtime.protocol_guard import ProtocolGuard
from runtime.memory_manager import MemoryManager
from runtime.tool_runner import run_tool, init_session


class GameEngine:
    """TRPG 游戏运行时引擎"""

    def __init__(self, skill_dir: str, llm: LLMClient):
        self.skill_dir = Path(skill_dir)
        self.llm = llm

        self.loop_schema = self._load_json("loop_schema.json")
        self.phase_scripts = self.loop_schema.get("phase_scripts", {})
        self.narrative_prompt_template = self.loop_schema.get("prompts", {}).get("narrative_prompt", "")
        self.agent_tools = self.loop_schema.get("agent_tools") or []
        # 内置工具：始终注入 advance_phase
        self.agent_tools.append({
            "type": "function",
            "function": {
                "name": "advance_phase",
                "description": "将游戏推进到下一个阶段。当你判断当前阶段的剧情已经完成、应该进入下一阶段时调用。目标阶段名可选。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "目标阶段名，留空则自动进入下一个阶段"}
                    },
                    "required": []
                }
            }
        })
        self.agents_md = self._load_text("AGENTS.md") or "# 无规则文件"

        self.config_mgr = ConfigManager(self.skill_dir / "game_config.json")
        self.config = self.config_mgr.data

        self.lorebook = LorebookManager(
            self.skill_dir / "lorebook.json", config=self.config
        )
        self.game_name = self.loop_schema.get("game_name", "")
        self.prompt_assembler = PromptAssembler(
            self.agents_md, self.lorebook, self.game_name
        )
        self.phase_machine = PhaseMachine(
            [PhaseSpec(name=p["name"],
                       next_phase=p.get("next"),
                       condition=p.get("condition", ""),
                       loop_variant=p.get("loop_variant", "default"))
             for p in self.loop_schema.get("phases", [])]
        )
        self.protocol_guard = ProtocolGuard(self.agents_md, self.config, self.llm)
        self.memory = MemoryManager(self.config, self.lorebook)

        self.state = GameState()
        self._load_or_init_state()
        self._last_narrative = ""
        self._turns_in_phase = 0

        self.static_system = self.prompt_assembler.system_prompt

    def _load_json(self, filename: str) -> dict:
        path = self.skill_dir / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _load_text(self, filename: str) -> str:
        path = self.skill_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _load_or_init_state(self):
        if getattr(self, '_state_loaded', False):
            return
        self._state_loaded = True
        autosave = self.skill_dir / "saves" / "autosave.json"
        if autosave.exists():
            try:
                data = json.loads(autosave.read_text(encoding="utf-8"))
                self.state = GameState.from_dict(data)
                if self.state.lorebook_state:
                    self.lorebook.restore_state(self.state.lorebook_state)
                return
            except Exception:
                pass
        try:
            init_session(self.skill_dir)
        except Exception:
            saves_dir = self.skill_dir / "saves"
            saves_dir.mkdir(parents=True, exist_ok=True)
            (saves_dir / "autosave.json").write_text(
                json.dumps(GameState().to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        try:
            self.state.turn = 1
            self.state.day = 1
            self.state.phase = self.phase_machine.current
            self._write_state()
        except Exception:
            import traceback
            traceback.print_exc()

    # ═══════════════════ 主循环 ═══════════════════

    def run_loop(self) -> Generator[dict, str, None]:
        steps = self.loop_schema.get("loop", [])
        if not steps:
            steps = _FALLBACK_LOOP
        safety = 0
        while True:
            safety += 1
            if safety > 500:
                yield {"type": "error", "content": "循环次数超限，游戏中断"}
                return

            old_phase = self.state.phase
            if self.phase_machine.tick(self.state, turns_in_phase=self._turns_in_phase):
                self.state.phase = self.phase_machine.current
            if self.state.phase != old_phase:
                self._turns_in_phase = 0

            for step in steps:
                step_type = step.get("type", "")

                if step_type == "read_state":
                    self._load_or_init_state()

                elif step_type == "route":
                    self._handle_route(step)

                elif step_type == "tool":
                    result = self._handle_tool(step)
                    if result:
                        yield result

                elif step_type == "llm_narrative":
                    narrative = self._generate_narrative()
                    self._last_narrative = narrative
                    yield {"type": "narrative", "content": narrative}

                elif step_type == "pause":
                    player_input = yield {"type": "wait_input"}
                    if player_input is None:
                        return
                    self.state.last_input = player_input

                elif step_type == "llm_process":
                    self._process_input()
                    self._turns_in_phase += 1

                elif step_type == "write_state":
                    self._write_state()

            self.state.turn += 1

    # ═══════════════════ 步骤处理 ═══════════════════

    def _handle_route(self, step: dict):
        route_map = step.get("route", {})
        if not route_map:
            return
        mode = self._get_time_mode()
        routed = route_map.get(mode, list(route_map.values())[0] if route_map else {})
        self.state.custom["routed_tool"] = routed.get("tool", "")

    def _get_time_mode(self) -> str:
        for step in self.loop_schema.get("loop", []):
            route = step.get("route", {})
            if route:
                keys = list(route.keys())
                if "day" in keys and "night" in keys:
                    return "day" if self.state.turn % 2 == 1 else "night"
                if keys:
                    idx = (self.state.turn - 1) % len(keys)
                    return keys[idx]
        return "default"

    def _handle_tool(self, step: dict) -> dict | None:
        tool_name = step.get("tool", "")
        if not tool_name:
            return None
        tool_name = tool_name.format(routed_tool=self.state.custom.get("routed_tool", ""))
        if not tool_name or tool_name == "{routed_tool}":
            return None
        tool_file = tool_name.split()[0]
        if not (self.skill_dir / "tools" / tool_file).exists():
            return None
        try:
            result = run_tool(self.skill_dir, tool_file,
                              args=tool_name.split()[1:])
            self.state.custom["last_tool_result"] = result
        except Exception:
            pass
        return None

    def _generate_narrative(self) -> str:
        """Agent 循环叙事生成：LLM 可调用工具查询数据，然后再生成叙事"""
        active_entries = self.lorebook.resolve(
            self.memory.build_messages(self.state),
            self.state,
            max_tokens=999999
        )

        context = pack_context(self.state, active_entries,
                               phase_scripts=self.phase_scripts)

        if self.narrative_prompt_template:
            try:
                extra_rules = self.phase_scripts.get(self.state.phase, [])
                rendered = self.narrative_prompt_template.format(
                    phase=self.state.phase,
                    location=self.state.player_location or "未知",
                    extra_rules="\n".join(f"- {s}" for s in extra_rules),
                    lorebook_context="",
                    state_snapshot="",
                )
                context = rendered + "\n\n" + context
            except (KeyError, ValueError):
                pass

        messages = self.memory.build_messages(self.state)
        messages.append({"role": "user", "content": context})

        temperature = self.config.get("narrative", {}).get("temperature", 0.9)
        max_tokens_out = self.config.get("narrative", {}).get("max_tokens", 0) or None
        tools = self.agent_tools if self.agent_tools else None

        max_rounds = 3
        for _ in range(max_rounds):
            try:
                resp = self.llm.chat_agent(
                    messages=messages,
                    system=self.static_system,
                    temperature=temperature,
                    max_tokens=max_tokens_out,
                    tools=tools,
                )
            except Exception as e:
                return f"[叙事生成失败: {e}]"

            # 无工具调用 → 返回叙事文本
            if not resp.tool_calls or not tools:
                return resp.content or "[空响应]"

            # 有工具调用 → 执行 → 追加结果 → 继续循环
            assistant_msg = {"role": "assistant", "content": resp.content or ""}
            if resp.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                    for tc in resp.tool_calls
                ]
            messages.append(assistant_msg)

            for tc in resp.tool_calls:
                result = self._execute_agent_tool(tc["name"], tc["arguments"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

        return resp.content or "[工具调用后无响应]"

    def _execute_agent_tool(self, name: str, args: dict) -> dict:
        """执行 Agent 工具函数（查询 Lorebook / 掷骰 / 随机抽取）"""
        if name == "list_items":
            t = args.get("type", "all")
            keyword = args.get("keyword", "")
            items = [e for e in self.lorebook.entries.values() if e.type == 'item']
            if t != "all":
                items = [e for e in items if t in (e.content[:40] + e.title)]
            if keyword:
                items = [e for e in items if keyword in (e.title + e.content[:80])]
            return {"items": [{"name": e.title, "brief": e.content[:100]} for e in items[:30]],
                    "total": len(items)}

        elif name == "get_item":
            n = args.get("name", "")
            for e in self.lorebook.entries.values():
                if e.type == 'item' and n in e.title:
                    return {"found": True, "name": e.title, "content": e.content}
            return {"found": False, "error": f"未找到物品: {n}"}

        elif name == "query_lorebook":
            t = args.get("type", "")
            keyword = args.get("keyword", "")
            entries = [e for e in self.lorebook.entries.values() if e.type == t] if t else list(self.lorebook.entries.values())
            if keyword:
                entries = [e for e in entries if keyword in (e.title + e.content[:120])]
            return {"results": [{"title": e.title, "content": e.content[:200]} for e in entries[:15]],
                    "total": len(entries)}

        elif name == "list_npcs":
            entries = [e for e in self.lorebook.entries.values() if e.type == 'npc']
            return {"npcs": [{"name": e.title, "brief": e.content[:100]} for e in entries[:20]],
                    "total": len(entries)}

        elif name == "advance_phase":
            target = args.get("target", "")
            old = self.state.phase
            if target and target in self.phase_machine.phases:
                self.phase_machine.set_phase(target)
            else:
                self.phase_machine.tick(self.state)
            self.state.phase = self.phase_machine.current
            # 返回当前阶段和可用脚本预览
            scripts = self.phase_scripts.get(self.state.phase, [])
            preview = scripts[:3] if scripts else []
            return {"ok": True, "from": old, "to": self.state.phase,
                    "phase_scripts_preview": preview}

        return {"error": f"未知工具: {name}"}

    def _process_input(self):
        """记录本轮到历史（不单独调 LLM，纯代码操作）"""
        self.state.history.append(TurnRecord(
            turn=self.state.turn,
            narrative=self._last_narrative,
            player_input=getattr(self.state, 'last_input', ''),
            phase=self.state.phase,
        ))

    def _write_state(self):
        self.state.phase = self.phase_machine.current
        self.state.lorebook_state = self.lorebook.get_state()
        self.state.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")

        saves_dir = self.skill_dir / "saves"
        saves_dir.mkdir(parents=True, exist_ok=True)

        autosave = saves_dir / "autosave.json"
        autosave.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def shutdown(self):
        self._write_state()
        self.llm.close()

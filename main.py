"""
TRPG-to-SKILL — AI驱动的TRPG剧本 → SKILL 自动编译 + 即时运行

用法:
    python main.py compile <世界书.txt> [--output <目录>]   # 编译模式
    python main.py play <SKILL目录>                          # CLI 游戏模式
    python main.py serve [--port 8641] [--game <目录>]       # Web 模式 (Phase 7)
    python main.py setup                                     # 首次运行: 配置API
"""
import argparse
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def cmd_compile(args):
    """编译模式: 世界书 → SKILL 目录"""
    from compiler.pipeline import compile
    input_file = args.input
    output_dir = args.output or os.path.join(PROJECT_ROOT, "generated", 
                                              os.path.splitext(os.path.basename(input_file))[0])
    compile(input_file, output_dir)


def cmd_play(args):
    """CLI 游戏模式"""
    from core.config_profiles import create_llm_from_profile
    from runtime.engine import GameEngine
    
    game_dir = args.game_dir
    llm = create_llm_from_profile()
    engine = GameEngine(game_dir, llm)
    
    print(f"\n  * {engine.loop_schema.get('game_name', 'TRPG')}")
    print(f"  /help | /quit\n")
    
    gen = engine.run_loop()
    try:
        response = next(gen)
        while True:
            if response["type"] == "narrative":
                print(response["content"])
            elif response["type"] == "system":
                print(f"  {response['content']}")
            elif response["type"] == "wait_input":
                user_input = input("\n> ").strip()
                response = _handle_cli_command(user_input, engine, gen)
                if response is None:
                    break
                continue
            elif response["type"] == "error":
                print(f"\n  FAIL {response['content']}")
                break
    except KeyboardInterrupt:
        print("\n\n  已中断。")
    except StopIteration:
        pass
    finally:
        engine.shutdown()


def _handle_cli_command(user_input, engine, gen):
    if user_input == "/quit":
        engine.shutdown()
        print("  [已保存] 再见。")
        return None
    elif user_input == "/help":
        print("""
  指令:
    /quit         退出游戏（自动存档）
    /save [名称]  手动存档
    /load <名称>  读取存档
    /saves        列出所有存档
    /status       显示游戏状态
    /hotreload    重新读取 SKILL 文件
    /summary      手动触发剧情摘要
    /config       查看/修改配置
    /debug on|off 切换调试信息
""")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input.startswith("/config"):
        return _handle_config(user_input, engine)
    elif user_input == "/debug on":
        engine.config["debug"]["show_token_usage"] = True
        engine.config["debug"]["show_lorebook_hits"] = True
        print("  OK 调试信息已开启")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input == "/debug off":
        engine.config["debug"]["show_token_usage"] = False
        engine.config["debug"]["show_lorebook_hits"] = False
        print("  OK 调试信息已关闭")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input == "/status":
        state = engine.state
        print(f"""
  轮次: {state.turn}  天数: {state.day}
  阶段: {state.phase}  位置: {state.player_location}
  活跃事件: {len(state.active_events)}
  NPC数: {len(state.npcs)}  库存: {len(state.inventory)} 件
""")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input == "/summary":
        engine.memory.force_summary()
        print("  OK 已生成剧情摘要")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input == "/hotreload":
        changed = engine.hot_reload.poll(engine.lorebook)
        if changed:
            print(f"  [RELOAD] 已热重载 {len(changed)} 个文件")
        else:
            print("  (无文件变更)")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input.startswith("/save"):
        parts = user_input.split(maxsplit=1)
        name = parts[1] if len(parts) > 1 else None
        engine.state.save_manual(name)
        print(f"  [已保存]")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input.startswith("/load"):
        parts = user_input.split(maxsplit=1)
        name = parts[1] if len(parts) > 1 else None
        if engine.state.load_manual(name):
            print(f"  [已读取] {name or '最新存档'}")
        else:
            print(f"  FAIL 存档不存在")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif user_input == "/saves":
        slots = engine.state.list_saves()
        for s in slots:
            print(f"  {s['name']}  ({s['turn']}轮, {s['date']})")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    else:
        try:
            return gen.send(user_input)
        except StopIteration:
            return None


def _handle_config(user_input, engine):
    parts = user_input.split()
    if len(parts) == 1:
        for key, value in engine.config.data.items():
            print(f"  {key} = {value}")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    elif parts[1] == "set" and len(parts) >= 4:
        key = parts[2]
        value = parts[3]
        try:
            engine.config_manager.update(key, float(value) if '.' in value else int(value))
            print(f"  OK {key} = {value}  (下一轮生效)")
        except ValueError as e:
            print(f"  FAIL {e}")
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)
    else:
        user_input = input("\n> ").strip()
        return engine._process_input(user_input)


def cmd_serve(args):
    """Web 模式"""
    from web.server import main as serve_main
    serve_main()


def cmd_setup(args):
    """首次运行: 引导配置 API"""
    from core.config_profiles import save_profile, activate, PROFILES_PATH
    print("\n  * TRPG-to-SKILL — 首次设置\n")
    name = input("  配置名称 [Default]: ").strip() or "Default"
    base_url = input("  API 地址 [https://api.deepseek.com/v1]: ").strip() or "https://api.deepseek.com/v1"
    api_key = input("  API Key: ").strip()
    model = input("  模型名 [deepseek-chat]: ").strip() or "deepseek-chat"
    analyzer_model = input("  分析用模型 (回车=同上): ").strip()
    save_profile(name, base_url, api_key, model, analyzer_model=analyzer_model)
    activate(name)
    print(f"\n  OK 配置已保存到 {PROFILES_PATH}")
    print(f"  OK 已激活配置: {name}")
    print(f"\n  现在可以运行:")
    print(f"    python main.py compile samples/example.txt")
    print(f"    python main.py play generated/example")


def main():
    parser = argparse.ArgumentParser(description="TRPG-to-SKILL")
    sub = parser.add_subparsers(dest="mode")

    p_compile = sub.add_parser("compile", help="编译世界书 → SKILL 目录")
    p_compile.add_argument("input", help="世界书文件路径 (.txt / .md)")
    p_compile.add_argument("--output", "-o", help="输出目录")

    p_play = sub.add_parser("play", help="CLI 游戏模式")
    p_play.add_argument("game_dir", help="SKILL 目录路径")

    p_serve = sub.add_parser("serve", help="Web 模式")
    p_serve.add_argument("--port", "-p", type=int, default=8641)
    p_serve.add_argument("--game", "-g", help="SKILL 目录路径")

    p_setup = sub.add_parser("setup", help="配置 API")

    args = parser.parse_args()

    if args.mode == "compile":
        cmd_compile(args)
    elif args.mode == "play":
        cmd_play(args)
    elif args.mode == "serve":
        cmd_serve(args)
    elif args.mode == "setup":
        cmd_setup(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

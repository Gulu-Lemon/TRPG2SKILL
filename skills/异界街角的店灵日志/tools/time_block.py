"""
time_block.py — 唯一调度器（每回合由引擎 route 调用）

读 autosave 快照 + last_input → 解析玩家意图 → 编排各确定性子系统 →
输出 {sim, state_patch, flags_to_set, events, g_events, narrative_hint, ...}。

设计要点（与引擎契约一致）：
- 纯函数：只读 autosave，不写 autosave；结果经 stdout → 引擎 last_tool_result。
- E1：引擎把 state_patch 并入顶层 custom、flags_to_set 并入 state.flags。
- 帧式推进：店灵能力/设计菜品/观察 不推进时间块；仅"推进/营业/打烊"等意图推进。
"""
import sys
import os
import json
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import saveio  # noqa: E402
import gamedata as G  # noqa: E402
import economy as E  # noqa: E402
import spirit as SP  # noqa: E402
import menu as M  # noqa: E402
import event_roller as EV  # noqa: E402
import progression as PR  # noqa: E402
import fast_forward as FF  # noqa: E402

ADVANCE_KW = ["开店", "开门", "营业", "打烊", "收摊", "关门", "下一个", "下一时间",
              "进入下一", "继续", "推进", "到午后", "到下午", "入夜", "到晚上", "天黑"]
FAST_KW = ["快进", "快速推进", "连播", "跳过", "快转"]
MENU_KW = ["设计", "新品", "配方", "研发", "菜单上加"]
NPC_NAMES = {"艾达": "ada", "莉涅": "line", "巴尔德": "bardo"}

# 观察路径的微细节池（按时间块分类），每回合轮换，防止 LLM 反复输出相同文字
_OBSERVE_HINTS = {
    "晨备": [
        "晨光从窗台那盆蓝色植物的叶片间漏进来，在吧台上划出一道窄窄的光斑。",
        "铜壶里的水开始咕噜作响。艾达揉了揉眼，把昨夜的账本塞进抽屉最深处。",
        "莉涅踮着脚把刚擦过的杯子一只只摆进柜子里，杯沿反射着窗外灰蓝色的天光。",
        "隔壁香料商那边飘来一阵新鲜的肉桂香，混进清晨的空气里。",
        "街上传来了第一辆马车的辘辘声——镇上醒了。",
    ],
    "午前营业": [
        "阳光慢慢爬过窗台，落在铜壶上。第一拨客人还没来，店里安静得能听见炉灶里木柴的噼啪声。",
        "一位老镇民推门进来，对艾达点了点头，径直朝老位置走去——他每天都坐那张桌子。",
        "莉涅端着热水壶给窗台上的蓝色植物加了一点水，小心翼翼得像在照顾小动物。",
        "铜铃轻响了一声，又归于沉寂——是风，不是客人。",
        "艾达用围裙角擦了擦磨豆机的手柄，那个动作她重复了成千上万次。",
    ],
    "午后营业": [
        "午后的阳光斜斜地照进来，把整个吧台染成了蜜色。巴尔德的背影在光里显得格外沉静。",
        "空气里咖啡的焦香和面包的麦香缠在一起，发酵成一种让人犯困的暖。",
        "莉涅抱着一摞刚洗好的杯子从后门进来，额角有一点细汗。",
        "窗外有孩子在街角追赶一只灰猫，影子在窗玻璃上一掠而过。",
        "有位客人把椅子往后挪了挪，发出一声满意的叹息，杯子已经空了。",
    ],
    "打烊后": [
        "最后一盏灯的灯芯微微跳动，把天花板的旧木梁染成暖橙色。街道已经完全安静了。",
        "艾达把今天的铜币一枚一枚码进匣子里，指尖在数字上停顿了一瞬。",
        "巴尔德用一块干净的布缓缓擦过吧台，那个动作像某种仪式。",
        "莉涅趴在桌上睡着了，辫子散了一缕，嘴角有一点咖啡渍——她偷喝了一口。",
        "窗外一片漆黑，只有小河的水声隐隐传来，像很远很远的叹息。",
    ],
}


def _observe_hint(sim: dict, turn: int) -> str:
    block = sim.get("block", "晨备")
    pool = _OBSERVE_HINTS.get(block, _OBSERVE_HINTS["晨备"])
    idx = turn % len(pool)
    return pool[idx]


def parse_days(text: str) -> int:
    num = ""
    for ch in text:
        if ch.isdigit():
            num += ch
        elif num:
            break
    return max(1, min(30, int(num))) if num else 3


def is_fast(text: str) -> bool:
    return any(k in text for k in FAST_KW)


def is_menu(text: str) -> bool:
    if any(k in text for k in MENU_KW):
        return True
    if "做" in text and any(i in text for i in G.INGREDIENT_PRICE):
        return True
    return False


def is_advance(text: str) -> bool:
    return any(k in text for k in ADVANCE_KW)


def _bump_bond(sim: dict, text: str, rng: random.Random) -> str | None:
    """成功能力涉及某 NPC 时，渐进推升其羁绊（约每 3 次升 1 星，蓝本 3.7）。"""
    for name, nid in NPC_NAMES.items():
        if name in text:
            npc = sim["npcs"][nid]
            if npc["bond_stars"] < 5 and rng.random() < 0.34:
                npc["bond_stars"] += 1
                return f'{name}的羁绊提升到 {G.bond_stars_str(npc["bond_stars"])}'
            return None
    return None


def _advance_block(sim: dict, rng: random.Random, out: dict, phase: str = "") -> None:
    SP.regen(sim)
    new_idx = (sim["block_idx"] + 1) % 4
    if new_idx == 0:  # 离开打烊后 → 次日
        sim["day"] += 1
        sim["today_in"] = 0
        sim["today_out"] = 0
        sim["events_today"] = []
        sim["weather"] = FF.roll_weather(sim["season"], rng)
        sim["special_day"] = "集市日" if sim["day"] % 6 == 0 else ""
        E.overnight_recovery(sim)
    sim["block_idx"] = new_idx
    sim["block"] = G.BLOCKS[new_idx]

    out["events"].extend(EV.roll_for_block(sim, sim["block"], rng, phase))

    if sim["block"] in ("午前营业", "午后营业"):
        out["block_result"] = E.simulate_business_block(sim, sim["block"], rng)
        SP.maybe_upgrade(sim)
    elif sim["block"] == "打烊后":
        out["settle"] = E.settle_day(sim, rng)
        sim["prosp_high_days"] = (sim.get("prosp_high_days", 0) + 1
                                  if sim["prosperity"] >= G.THRESHOLDS["P_ACT_3_PROSPERITY"]
                                  else 0)
        SP.maybe_upgrade(sim)


def dispatch(sim: dict, last_input: str, phase: str, turn: int,
             rng: random.Random) -> dict:
    out = {"events": [], "g_events": [], "narrative_hint": "", "player_hint": ""}
    text = (last_input or "").strip()

    # PROLOGUE_PART1: 现代世界 —— 不运行任何咖啡店模拟，不泄漏任何异世界数据
    if phase == "PROLOGUE_PART1":
        sim["started"] = True
        out["narrative_hint"] = ""
        out["player_hint"] = "输入你的名字和心境选择（A/B/C），或自由描述此刻。"
        out["sim"] = sim
        prog = PR.check(sim, phase)
        out["g_events"].extend(prog["g_events"])
        out["state_patch"] = saveio.project_patch(sim, phase)
        out["flags_to_set"] = prog["flags"]
        return out

    # 首回合：播种序章事件（PART2 首次进入咖啡店模拟）
    if not sim.get("started"):
        sim["started"] = True
        out["events"].extend(EV.roll_for_block(sim, sim["block"], rng, phase))
        out["narrative_hint"] = "序章·你在这间老咖啡店里醒来。感官逐层恢复，晨光里一切从模糊中显现。"
        out["player_hint"] = "你可以先感知周围，或试着做些什么。"

    if sim.get("mode") == "sleep":
        _advance_block(sim, rng, out, phase)
        if sim.get("mode") == "daily":
            out["narrative_hint"] = "你从沉睡中缓缓苏醒。沉睡期间店铺照常运转。"
        else:
            out["narrative_hint"] = f"店灵仍在沉睡（剩 {sim['sleep_left']} 时间块）。脚本自动运转，店铺照常。"
        out["player_hint"] = "沉睡中不可行动。"

    elif text and is_fast(text):
        days = parse_days(text)
        ff = FF.simulate_days(sim, days, rng, phase)
        out["fast_summary"] = ff
        if ff["interrupted"]:
            out["g_events"].append(ff["interrupt_event"])
            out["narrative_hint"] = ("你在快进中感到一阵晃动——某件重要的事正在发生，"
                                     "意识猛地回拢。" )
        else:
            out["narrative_hint"] = f"时间快进了 {ff['days_simulated']} 天。"
        out["player_hint"] = "已切回日常模式。"

    elif text and is_menu(text):
        d = M.design(text, sim)
        out["design_result"] = d
        if d.get("ok"):
            sim["menu"].append(d["item"])
            out["narrative_hint"] = f"新品【{d['item']['name']}】可以试做了，定价约 {d['price']} 铜。"
        else:
            out["narrative_hint"] = d["reason"]

    elif text and (ability := SP.match_ability(text, sim)) and not is_advance(text):
        res = SP.cast(ability, sim, rng)
        out["spirit_result"] = res
        out["narrative_hint"] = res.get("note") or res.get("reason", "")
        if res.get("ok") and res.get("success"):
            bond = _bump_bond(sim, text, rng)
            if bond:
                out["narrative_hint"] += f"（{bond}）"

    elif text and is_advance(text):
        _advance_block(sim, rng, out, phase)
        out["narrative_hint"] = f"时间推进到【{sim['block']}】。"

    else:
        hint = _observe_hint(sim, turn)
        out["narrative_hint"] = out["narrative_hint"] or hint
        out["player_hint"] = out["player_hint"] or "描述你想施加的影响，或说『推进/开店/打烊』继续。"

    # 进度与幕间
    prog = PR.check(sim, phase)
    out["g_events"].extend(prog["g_events"])

    out["sim"] = sim
    out["state_patch"] = saveio.project_patch(sim, phase)
    out["flags_to_set"] = prog["flags"]
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    state = saveio.read_autosave()
    sim = saveio.get_sim(state)
    last_input = (state or {}).get("last_input", "")
    phase = (state or {}).get("phase", "PROLOGUE")
    turn = (state or {}).get("turn", 1)
    # CLI 覆盖：python tools/time_block.py "<玩家输入>"  便于测试
    if len(sys.argv) > 1:
        last_input = sys.argv[1]
    rng = random.Random()
    out = dispatch(sim, last_input, phase, turn, rng)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

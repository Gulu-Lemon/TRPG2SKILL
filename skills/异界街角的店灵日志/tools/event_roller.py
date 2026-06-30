"""
event_roller.py — 事件池系统 A–F（蓝本十五）

按时间块转折点抽取事件：
  晨备结束 → B(天气) + C(季节/特殊日)
  营业块内 → A(日常微事件) + F(顾客事件)
  打烊后   → D(经济) + E(店员)
每类每日最多 1 次；每日总配额 2–4。G 类主线由 progression 处理，不在此。
"""
from __future__ import annotations
import random

# ── A 日常微事件（纯叙事，无系统效果）──
A_POOL = [
    ("a_cat", "门口的猫", "一只灰猫蹲在铜铃门帘下，懒洋洋地舔爪子。"),
    ("a_child", "跑过的孩童", "几个孩子追逐着跑过街角，笑声撞在窗玻璃上。"),
    ("a_smell", "邻铺的烟", "隔壁香料商那边飘来一阵辛香，和咖啡的焦香缠在一起。"),
    ("a_leaf", "蓝色植物", "窗台那盆叫不出名字的蓝色植物，悄悄落了一片叶子。"),
    ("a_hum", "莉涅哼歌", "莉涅一边擦桌子一边走调地哼着农家小调，没察觉自己出了声。"),
]
# ── F 顾客事件 ──
F_POOL = [
    ("f_adventurer", "落魄的前冒险者", "一个佩剑卷刃的男人坐下，摸遍口袋只有两枚铜币，眼里却装着一肚子故事。"),
    ("f_traveler", "异乡旅人", "风尘仆仆的旅人带来了山外的消息，说北边的路最近不太平。"),
    ("f_child", "带着幼儿的客人", "一位母亲抱着哭闹的婴儿进来，手忙脚乱地哄着，眼神里全是歉意。"),
    ("f_critic", "挑剔的食客", "衣着讲究的客人点了最贵的一样，默默品尝，不动声色地记着什么。"),
]
# ── D 经济事件 ──
D_POOL = [
    ("d_price_up", "食材涨价", "采买回来时，香料商说近来进货价涨了，某些食材怕是要贵些。"),
    ("d_harvest", "食材大丰收", "镇郊大丰收，集市上某种食材便宜得不像话，囤一些正合适。"),
    ("d_debt", "旧债上门", "一个陌生人拿着前任店主时期的旧借据，敲响了打烊后的门。"),
    ("d_repair", "街道翻修", "镇公所要翻修门前这段街道，往后几日门口都得绕着走。"),
]
# ── E 店员事件 ──
E_POOL = [
    ("e_skill", "技能精进", "打烊后，有人多练了一会儿手艺——明天的出品也许会更稳一点。"),
    ("e_quarrel", "小摩擦", "两位店员为一件小事拌了两句嘴，又很快各自闷头干活。"),
    ("e_warmth", "深夜的暖意", "收工时，有人默默给另一个人留了半杯还温着的咖啡。"),
    ("e_tired", "疲惫流露", "有人趴在吧台上打了个盹，被自己的鼾声惊醒，不好意思地笑了。"),
]
# ── B 天气事件（按当日天气）──
B_BY_WEATHER = {
    "暴雨": ("b_leak", "屋顶漏雨", "阁楼某处开始滴水，艾达找了个旧桶接着。两三个座位暂时不能坐了。"),
    "大风": ("b_sign", "招牌被吹歪", "门口的木招牌被风吹得吱呀作响，险些砸到路人。"),
    "雪": ("b_warm", "进店取暖", "一位老人推门进来取暖，捧着热茶讲起了镇上的旧事。"),
    "雾": ("b_lost", "走错路的客人", "一个客人在雾里走错了路，误打误撞推开了店门。"),
}
# ── C 特殊日事件 ──
C_BY_SPECIAL = {
    "集市日": ("c_market", "集市日", "河对面集市开张，食材批发价全线走低，人流也旺了不少。"),
}


def _hint(player: str = "") -> str:
    return player or "你可以选择施加某种影响，也可以只是看着，让世界自己回应。"


def _mk(entry, category, player_hint=""):
    eid, title, narr = entry
    return {"event_id": eid, "category": category, "title": title,
            "narrative_hint": narr, "player_hint": _hint(player_hint)}


def roll_for_block(sim: dict, block: str, rng: random.Random, phase: str = "") -> list[dict]:
    """为某时间块抽取事件，遵守每类每日≤1、每日总配额≤4。修改 sim['events_today']。
    防御性门控：PROLOGUE_PART1 期间不抽取任何事件（此时游戏尚未进入异世界）。"""
    if phase.startswith("PROLOGUE_PART1"):
        return []
    fired = sim.setdefault("events_today", [])
    events: list[dict] = []

    def can(cat: str) -> bool:
        return cat not in fired and len(fired) < 4

    if block == "晨备":
        # B：按天气必定（若该天气有对应条目）
        if can("B") and sim["weather"] in B_BY_WEATHER:
            events.append(_mk(B_BY_WEATHER[sim["weather"]], "B"))
            fired.append("B")
        # C：特殊日
        if can("C") and sim.get("special_day") in C_BY_SPECIAL:
            events.append(_mk(C_BY_SPECIAL[sim["special_day"]], "C"))
            fired.append("C")
    elif block in ("午前营业", "午后营业"):
        if can("A") and rng.random() < 0.30:
            events.append(_mk(rng.choice(A_POOL), "A"))
            fired.append("A")
        f_prob = 0.15 + sim["prosperity"] / 400.0
        if can("F") and rng.random() < f_prob:
            events.append(_mk(rng.choice(F_POOL), "F"))
            fired.append("F")
    elif block == "打烊后":
        d_prob = 0.25 + sim["prosperity"] / 300.0
        if can("D") and rng.random() < d_prob:
            events.append(_mk(rng.choice(D_POOL), "D"))
            fired.append("D")
        if can("E") and rng.random() < 0.35:
            events.append(_mk(rng.choice(E_POOL), "E"))
            fired.append("E")
    return events


if __name__ == "__main__":
    import sys, json, saveio
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(9)
    sim = saveio.default_sim()
    sim["weather"] = "暴雨"
    sim["prosperity"] = 50
    out = {b: [e["title"] for e in roll_for_block(sim, b, rng)]
           for b in ("晨备", "午前营业", "午后营业", "打烊后")}
    print(json.dumps({"events": out, "fired": sim["events_today"]}, ensure_ascii=False))

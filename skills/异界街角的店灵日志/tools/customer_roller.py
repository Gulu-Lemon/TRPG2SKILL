"""
customer_roller.py — 顾客生成引擎（蓝本十四）

确定性矩阵抽样：种族/年龄/阶层/职业/性格/预算/期望。
输出结构化顾客列表，供 quality 出餐结算与 LLM 叙事展开。
"""
from __future__ import annotations
import random

import gamedata as G
import prosperity as P

AGE_WEIGHTS = {"少年": 15, "青年": 45, "壮年": 30, "老年": 10}
AGE_SPEND = {"少年": 0.6, "青年": 1.0, "壮年": 1.3, "老年": 0.9}

OCCUPATION = {
    "平民": ["农夫", "杂工", "学徒", "送信人", "渔夫", "搬运工", "佣人", "街头小贩"],
    "市民": ["铁匠", "面包师", "裁缝", "文员", "教师", "卫兵", "抄写员", "小店主"],
    "商人": ["行商", "批发商", "供应商", "旅店老板", "公会办事员", "放贷人"],
    "上层": ["富商", "地主", "低阶贵族", "镇议员", "矿场主", "高阶军官"],
    "贵宾": ["高阶贵族", "名人", "外邦使节", "高阶法师", "稀客旅者"],
}
PERSONALITY = ["开朗", "阴郁", "热情", "冷淡", "话多", "寡言", "随和", "挑剔",
               "急性", "慢性", "好奇", "传统", "慷慨", "吝啬"]
EXCLUSIVE = [{"话多", "寡言"}, {"急性", "慢性"}, {"开朗", "阴郁"},
             {"热情", "冷淡"}, {"慷慨", "吝啬"}]
SUBSPECIES = ["猫耳", "犬耳", "狐尾", "兔耳", "熊耳", "狼耳", "鸟翼", "鹿角", "蛇瞳", "鬃毛"]
HAIR = ["棕", "金", "黑", "红", "灰", "银白", "栗"]


def _pick_personalities(rng: random.Random) -> list[str]:
    first = rng.choice(PERSONALITY)
    tags = [first]
    if rng.random() < 0.5:
        for _ in range(6):
            cand = rng.choice(PERSONALITY)
            if cand == first:
                continue
            if any(cand in pair and first in pair for pair in EXCLUSIVE):
                continue
            tags.append(cand)
            break
    return tags


def _appearance(species: str, age: str, occupation: str, rng: random.Random) -> list[str]:
    out = []
    if species == "亚人":
        out.append(f"{rng.choice(SUBSPECIES)}亚人")
    out.append(f"{rng.choice(HAIR)}发")
    out.append({"少年": "稚气未脱", "青年": "干练", "壮年": "沉稳", "老年": "佝偻"}[age])
    out.append(f"像个{occupation}")
    return out


def roll_customer(prosperity: int, rng: random.Random, cid: int) -> dict:
    tier = P.roll_tier(prosperity, rng)
    species = "人类" if rng.random() < 0.5 else "亚人"
    age = rng.choices(list(AGE_WEIGHTS), weights=list(AGE_WEIGHTS.values()), k=1)[0]
    occupation = rng.choice(OCCUPATION[tier])
    lo, hi = G.TIER_BUDGET[tier]
    budget = max(2, int(rng.randint(lo, hi) * AGE_SPEND[age]))
    return {
        "id": f"cust_{cid:04d}",
        "tier": tier,
        "species": species,
        "age": age,
        "occupation": occupation,
        "personality": _pick_personalities(rng),
        "budget": budget,
        "expectation": G.TIER_EXPECTATION[tier],   # 0..2 等级
        "appearance": _appearance(species, age, occupation, rng),
    }


def block_count(sim: dict, block: str, rng: random.Random) -> int:
    """计算某营业时间块的潜在顾客数（蓝本 14.5，按块拆分）。"""
    if block == "午前营业":
        base = rng.randint(4, 7)
    elif block == "午后营业":
        base = rng.randint(6, 10)
    else:
        return 0
    w = G.WEATHER_FLOW.get(sim["weather"], 1.0)
    s = G.SEASON_FLOW.get(sim["season"], 1.0)
    if sim.get("special_day") == "集市日":
        s *= 1.5
    bonus = int(sim["prosperity"]) // 14
    count = int(base * w * s) + bonus
    return max(0, min(14, count))


def roll_block_customers(sim: dict, block: str, rng: random.Random) -> list[dict]:
    n = block_count(sim, block, rng)
    out = []
    nid = sim.get("customers", {}).get("next_id", 1)
    for _ in range(n):
        out.append(roll_customer(sim["prosperity"], rng, nid))
        nid += 1
    sim.setdefault("customers", {})["next_id"] = nid
    return out


if __name__ == "__main__":
    import sys, json
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import saveio
    rng = random.Random(7)
    sim = saveio.default_sim()
    sim["prosperity"] = 45
    sim["block"] = "午后营业"
    custs = roll_block_customers(sim, "午后营业", rng)
    print(json.dumps({"count": len(custs), "sample": custs[:2]}, ensure_ascii=False))

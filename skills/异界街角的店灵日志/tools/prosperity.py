"""
prosperity.py — 繁荣度系统（蓝本 11.3 / 13.3 / 14.3）

纯函数：繁荣度增减、口碑标签、按繁荣度分层抽取顾客阶层。
"""
from __future__ import annotations
import random
import gamedata as G


def apply_delta(sim: dict, delta: int) -> int:
    """增减繁荣度并裁剪到 [0,100]，返回新值。"""
    sim["prosperity"] = max(0, min(100, int(sim["prosperity"]) + int(delta)))
    return sim["prosperity"]


def reputation(prosperity: int) -> str:
    return G.reputation_label(prosperity)


def roll_tier(prosperity: int, rng: random.Random) -> str:
    """按当前繁荣度分布加权抽取一个顾客阶层。"""
    dist = G.tier_distribution(prosperity)
    tiers = list(dist.keys())
    weights = list(dist.values())
    return rng.choices(tiers, weights=weights, k=1)[0]


def spirit_regen_bonus(stage: int, prosperity: int) -> int:
    """SP 恢复的繁荣度加成（蓝本 3.1）。"""
    divisor = {2: 20, 3: 15, 4: 10}.get(stage)
    if not divisor:
        return 0
    return prosperity // divisor


if __name__ == "__main__":
    import sys, json
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(42)
    sample = {p: roll_tier(p, rng) for p in (10, 30, 55, 85)}
    print(json.dumps({"reputation_85": reputation(85), "tier_samples": sample,
                      "regen_bonus_s3_p60": spirit_regen_bonus(3, 60)},
                     ensure_ascii=False))

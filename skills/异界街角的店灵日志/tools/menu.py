"""
menu.py — 菜单定价与菜品自由设计（蓝本十二）

定价公式（12.4）：
  售价 = 食材成本 × 复杂度系数 × 品质系数 × 新品系数 × 繁荣度系数 → 取整到 0.5 铜
"""
from __future__ import annotations
import gamedata as G

SKILL_KEYS = {"咖啡": "coffee", "茶": "tea", "面包": "bake", "烘焙": "bake"}
HIGH_INGREDIENTS = {"咖啡豆精选", "可可粉", "香草荚", "蜂蜜", "奶油", "花茶"}
SPECIAL_INGREDIENTS = {"安宁草", "晨露花蜜", "星辰糖晶"}


def ingredient_cost(recipe: dict) -> float:
    return sum(G.INGREDIENT_PRICE.get(name, 1) * qty for name, qty in recipe.items())


def best_skill(sim: dict, skill_key: str) -> int:
    return max((n["skills"].get(skill_key, 0) for n in sim["npcs"].values()), default=0)


def quality_coef(skill: int) -> float:
    return max(0.7, min(1.3, 0.7 + 0.1 * (skill - 3)))


def new_coef(item: dict, day: int) -> float:
    since = item.get("new_since_day", 0)
    if since and since > 0:
        age = day - since
        if age <= 3:
            return 1.2
        if age <= 7:
            return 1.1
    return 1.0


def prosperity_coef(prosperity: int) -> float:
    for ceil, coef in [(20, 0.85), (40, 0.95), (60, 1.05), (80, 1.15), (101, 1.2)]:
        if prosperity < ceil:
            return coef
    return 1.2


def price(item: dict, sim: dict) -> float:
    cost = ingredient_cost(item["recipe"])
    comp = G.COMPLEXITY_COEF.get(item.get("complexity", "简单"), 2.0)
    qc = quality_coef(best_skill(sim, item.get("skill", "coffee")))
    nc = new_coef(item, sim["day"])
    pc = prosperity_coef(sim["prosperity"])
    raw = cost * comp * qc * nc * pc
    if any(i in SPECIAL_INGREDIENTS for i in item["recipe"]):
        raw *= 1.5
    return round(raw * 2) / 2  # 取整到 0.5 铜


def complexity_of(recipe: dict, category: str) -> str:
    n = len(recipe)
    if category == "烘焙":
        return "简单" if n <= 3 else ("中等" if n <= 5 else "复杂")
    return "简单" if n <= 2 else ("中等" if n <= 4 else "复杂")


def design(intent: str, sim: dict) -> dict:
    """从玩家自然语言意图设计新菜品（蓝本 12.3）。

    需店灵 ≥ 二阶；食材须在库存可得；至少一名店员技能达标。
    """
    if sim["spirit"]["stage"] < 2:
        return {"ok": False, "reason": "店灵尚在一阶，还无法向店员传达新配方（需二阶）。"}

    found = {name: 1 for name in G.INGREDIENT_PRICE if name in intent}
    if not found:
        return {"ok": False, "reason": "没听出要用哪些食材，请说得更具体一些。",
                "needs_clarification": True}

    missing = [n for n in found if sim["inventory"].get(n, 0) <= 0]
    if missing:
        return {"ok": False, "reason": f"库存里没有：{'、'.join(missing)}。"}

    if any(k in found for k in ("面粉", "黑麦粉")):
        category, skill = "烘焙", "bake"
    elif "茶叶" in found or "花茶" in found:
        category, skill = "热饮", "tea"
    else:
        category, skill = "热饮", "coffee"
    if "柴火" not in found:
        found["柴火"] = 1

    complexity = complexity_of(found, category)
    need_skill = {"简单": 1, "中等": 3, "复杂": 5}[complexity]
    if best_skill(sim, skill) < need_skill:
        return {"ok": False,
                "reason": f"目前没有店员能稳定做出这种{complexity}菜品（需{skill}技能≥{need_skill}）。",
                "as_goal": True}

    item = {"name": intent.strip()[:12] or "新品", "category": category,
            "skill": skill, "complexity": complexity, "recipe": found,
            "new_since_day": sim["day"]}
    item_price = price(item, sim)
    return {"ok": True, "item": item, "price": item_price,
            "note": f"可由{'巴尔德' if skill == 'coffee' else '店员'}试做的新品。"}


if __name__ == "__main__":
    import sys, json, saveio
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sim = saveio.default_sim()
    prices = {it["name"]: price(it, sim) for it in sim["menu"]}
    sim["spirit"]["stage"] = 2
    sim["inventory"]["蜂蜜"] = 5
    sim["inventory"]["肉桂"] = 5
    d = design("用蜂蜜和肉桂做一杯热咖啡", sim)
    print(json.dumps({"initial_prices": prices, "design": d}, ensure_ascii=False))

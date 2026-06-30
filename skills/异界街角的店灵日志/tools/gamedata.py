"""
gamedata.py — 《异界街角的店灵日志》静态游戏数据与常量

所有确定性工具共享的不可变数据：食材价格、初始菜单、初始 NPC、
店灵能力表、繁荣度阈值/分层、顾客生成矩阵等。
对应设计蓝本第三/十一/十二/十三/十四章。

本模块不持有运行时状态，仅提供数据与纯函数，便于被其它工具 import 及单测。
"""
from __future__ import annotations

# ── 货币 ──────────────────────────────────────────────
COPPER_PER_SILVER = 100
STARTING_BALANCE = 600  # 6 银，约可维持 7-10 天（蓝本 11.2.1）

# ── 繁荣度阈值常量（蓝本 11.3.2）────────────────────────
THRESHOLDS = {
    "P_RECRUIT": 20,
    "P_SPIRIT_2": 25,
    "P_ACT_1_EXIT": 35,
    "P_RICH_MERCHANT": 35,
    "P_FAST_RECRUIT": 40,
    "P_SPIRIT_3": 50,
    "P_COMPETITOR": 50,
    "P_BUYOUT": 60,
    "P_ACT_2_EXIT": 60,
    "P_SPIRIT_4": 75,
    "P_ACT_3_PROSPERITY": 80,
}

# ── 时间块与季节 ───────────────────────────────────────
BLOCKS = ["晨备", "午前营业", "午后营业", "打烊后"]
SEASONS = ["春", "夏", "秋", "冬"]
WEATHERS = ["晴", "小雨", "暴雨", "大风", "雪", "凉爽", "雾"]
# 客流天气系数（蓝本 14.5）
WEATHER_FLOW = {"晴": 1.0, "小雨": 0.8, "暴雨": 0.4, "大风": 0.7,
                "雪": 0.5, "凉爽": 1.1, "雾": 0.9}
SEASON_FLOW = {"春": 1.0, "夏": 0.9, "秋": 1.1, "冬": 0.7}
# 各季天气抽取权重
SEASON_WEATHER_WEIGHTS = {
    "春": {"晴": 5, "小雨": 3, "大风": 2, "凉爽": 2, "雾": 1},
    "夏": {"晴": 5, "暴雨": 2, "小雨": 2, "凉爽": 1},
    "秋": {"晴": 5, "凉爽": 3, "小雨": 2, "大风": 2, "雾": 1},
    "冬": {"晴": 3, "雪": 4, "大风": 2, "小雨": 1},
}

# ── 食材基础单价（铜/份，蓝本 12.2）────────────────────
INGREDIENT_PRICE = {
    "咖啡豆": 2, "咖啡豆精选": 5, "茶叶": 1, "花茶": 3, "可可粉": 6,
    "牛奶": 2, "奶油": 3, "砂糖": 1, "蜂蜜": 3, "肉桂": 2, "香草荚": 8,
    "薄荷叶": 2, "生姜": 1, "盐": 0.5, "面粉": 1, "黑麦粉": 1.5,
    "鸡蛋": 2, "黄油": 3, "酵母": 1, "草莓": 3, "浆果": 3, "苹果": 2,
    "柑橘": 3, "干果": 2, "坚果": 3, "果酱": 4, "柴火": 0.5,
}
# 库存上限（蓝本 11.2.5）
INGREDIENT_CAP = {
    "咖啡豆": 50, "茶叶": 30, "牛奶": 20, "奶油": 15, "砂糖": 30, "面粉": 30,
    "鸡蛋": 20, "黄油": 15, "盐": 20, "蜂蜜": 10, "肉桂": 10, "柴火": 40,
}
# 开局库存
STARTING_INVENTORY = {
    "咖啡豆": 40, "茶叶": 20, "牛奶": 8, "砂糖": 20, "面粉": 15,
    "鸡蛋": 10, "黄油": 8, "盐": 15, "柴火": 30,
}

# ── 初始菜单（蓝本 12.1）──────────────────────────────
# recipe: {食材: 份量}; category: 热饮/烘焙; skill: 对应技能键; complexity: 简单/中等/复杂
INITIAL_MENU = [
    {"name": "黑咖啡", "category": "热饮", "skill": "coffee", "complexity": "简单",
     "recipe": {"咖啡豆": 1, "柴火": 1}, "new_since_day": 0},
    {"name": "牛奶咖啡", "category": "热饮", "skill": "coffee", "complexity": "简单",
     "recipe": {"咖啡豆": 1, "牛奶": 1, "柴火": 1}, "new_since_day": 0},
    {"name": "热茶", "category": "热饮", "skill": "tea", "complexity": "简单",
     "recipe": {"茶叶": 1, "柴火": 1}, "new_since_day": 0},
    {"name": "素面包", "category": "烘焙", "skill": "bake", "complexity": "简单",
     "recipe": {"面粉": 1, "盐": 0.5, "柴火": 1}, "new_since_day": 0},
    {"name": "黄油面包", "category": "烘焙", "skill": "bake", "complexity": "简单",
     "recipe": {"面粉": 1, "黄油": 1, "盐": 0.5, "柴火": 1}, "new_since_day": 0},
]

COMPLEXITY_COEF = {"简单": 2.0, "中等": 2.5, "复杂": 3.0}

# ── 初始 NPC（蓝本四 / 11.5）──────────────────────────
INITIAL_NPCS = {
    "ada": {"name": "艾达", "fatigue": 20, "morale": 60, "bond_stars": 0,
            "wage": 25, "owed_days": 0,
            "skills": {"coffee": 4, "tea": 3, "bake": 3, "serve": 4}},
    "line": {"name": "莉涅", "fatigue": 10, "morale": 55, "bond_stars": 0,
             "wage": 15, "owed_days": 0,
             "skills": {"coffee": 2, "tea": 2, "bake": 1, "serve": 2}},
    "bardo": {"name": "巴尔德", "fatigue": 15, "morale": 70, "bond_stars": 0,
              "wage": 35, "owed_days": 0,
              "skills": {"coffee": 6, "tea": 4, "bake": 4, "serve": 2}},
}
BOND_NAMES = ["陌路", "察觉", "好奇", "信任", "羁绊", "至交"]


def bond_stars_str(n: int) -> str:
    n = max(0, min(5, int(n)))
    return "★" * n + "☆" * (5 - n)


# ── 店灵能力（蓝本 3.1 - 3.5）─────────────────────────
SP_TABLE = {
    1: {"max": 15, "regen": 2, "fail": 40, "perception": "吧台3米内"},
    2: {"max": 35, "regen": 4, "fail": 20, "perception": "整个一楼"},
    3: {"max": 60, "regen": 7, "fail": 5, "perception": "整栋建筑+门前街道"},
    4: {"max": 100, "regen": 10, "fail": 0, "perception": "小镇一角"},
}

# 能力定义：stage 为解锁阶段；syn 为玩家自然语言意图的关键词；
# sleep 为沉睡时间块数（0=不沉睡）；bond 为羁绊门槛星数
SPIRIT_ABILITIES = [
    {"id": "微光", "stage": 1, "sp": 1, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["灯", "烛", "火光", "闪", "明灭", "微光"],
     "effect": "让一盏灯或烛火明灭一次"},
    {"id": "轻推", "stage": 1, "sp": 2, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["推", "移动", "滚", "掀", "信", "纸", "杯子", "硬币", "注意到"],
     "effect": "让一个轻小物体微微移动或滚落"},
    {"id": "温变", "stage": 1, "sp": 1, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["温度", "变暖", "变凉", "热气", "暖一点", "凉一点"],
     "effect": "让一个杯/壶/碗的温度轻微升降"},
    {"id": "穿隙风", "stage": 1, "sp": 2, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["风", "窗", "门", "开合", "气流"],
     "effect": "让一扇虚掩的窗或门自己开合"},
    {"id": "气氛微调", "stage": 2, "sp": 6, "cd": 1, "sleep": 0, "bond": 0,
     "syn": ["气氛", "氛围", "舒适", "温暖", "清爽"],
     "effect": "店内整体氛围偏向舒适/温暖/清爽"},
    {"id": "风味暗示", "stage": 2, "sp": 4, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["风味", "味道", "更好喝", "苦", "柔和", "提味"],
     "effect": "正在制作的饮品/糕点风味微偏"},
    {"id": "直觉播种", "stage": 2, "sp": 10, "cd": 2, "sleep": 0, "bond": 2,
     "syn": ["直觉", "暗示", "总觉得", "灵感", "念头"],
     "effect": "在 NPC 放松时植入模糊直觉"},
    {"id": "暖意", "stage": 2, "sp": 3, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["暖意", "照看", "被照顾", "座椅", "茶杯变暖"],
     "effect": "让一名 NPC 周围短暂变暖，传递被照看感"},
    {"id": "梦境造访", "stage": 3, "sp": 18, "cd": 3, "sleep": 0, "bond": 3,
     "syn": ["梦", "梦境", "意象", "画面"],
     "effect": "NPC 梦里出现模糊意象场景"},
    {"id": "敏锐感知", "stage": 3, "sp": 5, "cd": 0, "sleep": 0, "bond": 0,
     "syn": ["感知", "街道", "偷听", "听见", "延伸"],
     "effect": "感知范围暂时延伸至店外街道"},
    {"id": "笨拙庇护", "stage": 3, "sp": 12, "cd": 1, "sleep": 0, "bond": 0,
     "syn": ["庇护", "稳住", "接住", "别摔", "滞空", "打翻"],
     "effect": "小意外瞬间减缓冲击"},
    {"id": "羁绊共鸣", "stage": 3, "sp": 8, "cd": 2, "sleep": 0, "bond": 3,
     "syn": ["共鸣", "感受到我", "存在", "善意的存在"],
     "effect": "让结下羁绊的 NPC 短暂感知到店灵存在"},
    {"id": "配方印记", "stage": 3, "sp": 15, "cd": 4, "sleep": 2, "bond": 0,
     "syn": ["印记", "字迹", "配方痕迹", "草图", "浮现"],
     "effect": "平面上浮现逐渐消退的字迹/图案"},
    {"id": "虚像显现", "stage": 4, "sp": 30, "cd": 6, "sleep": 6, "bond": 0,
     "syn": ["显现", "虚像", "现身", "被看到", "人形"],
     "effect": "昏暗中短暂显现模糊人形（必定沉睡）"},
    {"id": "梦境对话", "stage": 4, "sp": 25, "cd": 6, "sleep": 4, "bond": 4,
     "syn": ["梦里说", "对话", "告诉她", "说话"],
     "effect": "NPC 梦中进行一次双向对话"},
    {"id": "店之加护", "stage": 4, "sp": 60, "cd": 12, "sleep": 8, "bond": 0,
     "syn": ["加护", "安全屋", "屏障", "守护全店"],
     "effect": "整间店化为临时安全屋（必定沉睡）"},
]

# ── 顾客分层（蓝本 14.3 / 13.3）───────────────────────
# 繁荣度分层分布：(上限, {阶层: 权重})
TIER_BANDS = [
    (20, {"平民": 75, "市民": 25}),
    (40, {"平民": 55, "市民": 33, "商人": 12}),
    (60, {"平民": 40, "市民": 35, "商人": 20, "上层": 5}),
    (80, {"平民": 30, "市民": 35, "商人": 25, "上层": 8, "贵宾": 2}),
    (101, {"平民": 25, "市民": 35, "商人": 25, "上层": 12, "贵宾": 3}),
]
TIER_BUDGET = {  # 铜，消费预算区间
    "平民": (3, 8), "市民": (8, 20), "商人": (20, 50),
    "上层": (50, 120), "贵宾": (80, 200),
}
# 期望品质等级（0平凡 1优质 2精品 3完美）
TIER_EXPECTATION = {"平民": 0, "市民": 1, "商人": 1, "上层": 2, "贵宾": 2}
QUALITY_LEVELS = ["平凡", "优质", "精品", "完美"]

# 满意度（蓝本 13.4）：实际-期望差 → 标签与繁荣度Δ
SATISFACTION = {
    2: ("AMAZED", "惊艳", 3),
    1: ("PLEASED", "愉悦", 1),
    0: ("SATISFIED", "满意", 0),
    -1: ("DISAPPOINTED", "失望", -1),
    -2: ("OFFENDED", "厌恶", -3),
}

# ── 薪资（蓝本 11.2.3）发放顺序：莉涅→巴尔德→艾达 ──
WAGE_ORDER = ["line", "bardo", "ada"]

REPUTATION_LABELS = [
    (9, "无人知晓"), (19, "街角小店"), (34, "初具名声"), (49, "小有名气"),
    (64, "有口皆碑"), (79, "远近闻名"), (94, "全镇第一"), (100, "传奇老店"),
]


def reputation_label(prosperity: int) -> str:
    for ceil, label in REPUTATION_LABELS:
        if prosperity <= ceil:
            return label
    return "传奇老店"


def tier_distribution(prosperity: int) -> dict:
    for ceil, dist in TIER_BANDS:
        if prosperity < ceil:
            return dist
    return TIER_BANDS[-1][1]


def fmt_money(copper: int) -> str:
    copper = int(round(copper))
    sign = "-" if copper < 0 else ""
    copper = abs(copper)
    s, c = divmod(copper, COPPER_PER_SILVER)
    if s:
        return f"{sign}{s}银{c}铜"
    return f"{sign}{c}铜"

# TRPG2SKILL v1.1.0-beta

将 TRPG 世界书转化为可运行的 AI 驱动文字冒险游戏。

## 快速开始

### 1. 安装 Python 3.12+

从 https://www.python.org/ 下载。

### 2. 获取 TRPG2SKILL

```bash
git clone https://github.com/Gulu-Lemon/TRPG2SKILL.git
cd TRPG2SKILL
```

或下载 ZIP 压缩包解压。

### 3. 启动

双击 `start.bat`，选择 `[1] Web GUI`。

依赖库在首次运行时自动安装。Web 界面打开后访问 http://127.0.0.1:8641。

### 4. 配置 API

进入 **设置** 页面，填写 API 凭据并保存。

### 5. 加载游戏

在 **游玩** 页面，从 **技能(Skills)** 列表（手写成品游戏）或 **已编译(Generated)** 列表（编译产物）中选择一个游戏，点击 **开始新游戏**。

## 预装游戏：《异界街角的店灵日志》

使用 TRPG2SKILL 框架开发的完整可玩 TRPG 游戏：

> 现代灵魂重生为中世纪异世界街角咖啡店的"店灵"，通过全知视角观察、间接影响店铺与店员，在经营咖啡店的日常中逐步觉醒，最终面对"以何种形式存在于这个世界"的终极抉择。

**剧情结构：**
- **序章**（5 个子阶段）：现代世界 → 死亡 → 苏醒 → 店铺命名 → 巴尔德回归
- **第一幕** *"不关我的事"*：学习成为店灵，逐渐在意这些人和这间店
- **第二幕** *"这是我的店"*：繁荣度上升，神秘发现，分歧选择
- **第三幕** *"我是什么"*：勇者到来，起源真相揭开
- **终局**：基于玩家选择的多结局

**数值引擎：** 14 个确定性工具（时间块调度器、经济模拟、繁荣度系统、顾客生成、品质评分、灵力/阶段成长、事件池等）

## 使用方式

| 模式 | 方法 |
|------|------|
| **Web 界面** | `start.bat` → `[1]` |
| **CLI 编译** | `python main.py compile world_book.txt` |
| **API 配置** | `python main.py setup` |

## 更新

```bash
cd TRPG2SKILL
git pull
pip install -r requirements.txt
```

或双击 `update.bat`。

## 项目结构

```
TRPG2SKILL/
├── core/          # LLM 客户端、状态管理、配置
├── compiler/      # 世界书 → SKILL 编译管线（5 阶段 LLM + 验证）
├── runtime/       # 游戏引擎、Lorebook、智能体循环、阶段机
├── web/           # Flask 服务器 + 单页前端（HUD、Markdown 渲染、主题）
├── skills/        # 手写成品游戏脚本（受版本管理）
│   └── 异界街角的店灵日志/   # 完整游戏——序章到终局
├── generated/     # 编译输出（git 忽略）
├── samples/       # 示例世界书
└── start.bat      # 启动器
```

## 运行要求

- Python 3.12+
- httpx、jinja2、flask（自动安装）
- 兼容 OpenAI 的 API（DeepSeek、OpenAI 等）

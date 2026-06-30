# TRPG2SKILL v1.1.0-beta

Convert TRPG world books into runnable AI-powered text adventure games.

## Quick Start

### 1. Install Python 3.12+

Download from https://www.python.org/

### 2. Download TRPG2SKILL

```bash
git clone https://github.com/Gulu-Lemon/TRPG2SKILL.git
cd TRPG2SKILL
```

Or download the zip and extract it.

### 3. Launch

Double-click `start.bat` and choose `[1] Web GUI`.

Dependencies are installed automatically on first run. The web interface opens at http://127.0.0.1:8641.

### 4. Configure API

Click the **Settings** tab, fill in your API credentials, and click **Save**.

### 5. Load a game

From the **Play** tab, select a game from the **Skills** list (hand-written games) or **Generated** list (compiled outputs), then click **Start New Game**.

## Included Game: 《异界街角的店灵日志》

A fully-playable TRPG built with the TRPG2SKILL framework:

> 现代灵魂重生为中世纪异世界街角咖啡店的"店灵"，通过全知视角观察、间接影响店铺与店员，在经营咖啡店的日常中逐步觉醒，最终面对"以何种形式存在于这个世界"的终极抉择。

**Structure:**
- **Prologue** (5 sub-phases): Modern world → death → awakening → shop naming → Bardo's return
- **Act 1** *"Not My Problem"*: Learning to be a shop spirit, gradual attachment
- **Act 2** *"This Is My Shop"*: Rising prosperity, mysterious discoveries, diverging paths
- **Act 3** *"What Am I?"*: The hero arrives, origin truth revealed
- **Ending**: Multiple endings based on choices

**Numeric engine:** 14 deterministic tools (time-block scheduler, economy simulation, prosperity system, customer roller, quality scoring, SP/stage progression, event pools, etc.)

To play: select `异界街角的店灵日志` from the Skills list on the Play tab.

## Usage

| Mode | How |
|------|-----|
| **Web GUI** | `start.bat` → `[1]` |
| **CLI Compile** | `python main.py compile world_book.txt` |
| **API Setup** | `python main.py setup` |

## Update

```bash
cd TRPG2SKILL
git pull
pip install -r requirements.txt
```

Or double-click `update.bat`.

## Project Structure

```
TRPG2SKILL/
├── core/          # LLM client, state management, config
├── compiler/      # World book → SKILL pipeline (5-phase LLM + validation)
├── runtime/       # Game engine, lorebook, agent loop, phase machine
├── web/           # Flask server + SPA frontend (HUD, markdown, themes)
├── skills/        # Hand-written game scripts (version-controlled)
│   └── 异界街角的店灵日志/   # Full game — prologue → ending
├── generated/     # Compiled SKILL output (gitignored)
├── samples/       # Example world books
├── autoplay/      # Automated playtesting (gitignored)
└── start.bat      # Launcher
```

## Requirements

- Python 3.12+
- httpx, jinja2, flask (auto-installed)
- An OpenAI-compatible API (DeepSeek, OpenAI, etc.)

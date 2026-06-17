# TRPG2SKILL v1.0.0-beta

Convert TRPG world books into runnable AI-powered text adventure games.

## Quick Start

### 1. Install Python 3.12+

Download from https://www.python.org/

### 2. Download TRPG2SKILL

```bash
git clone https://github.com/your-username/TRPG2SKILL.git
cd TRPG2SKILL
```

Or download the zip and extract it.

### 3. Launch

Double-click `start.bat` and choose `[1] Web GUI`.

Dependencies are installed automatically on first run. The web interface opens at http://127.0.0.1:8641.

### 4. Configure API

Click the **Settings** tab, fill in your API credentials, and click **Save**.

## Usage

| Mode | How |
|------|-----|
| **Web GUI** | `start.bat` → `[1]` |
| **CLI Compile** | `python main.py compile world_book.txt` |
| **CLI Play** | `python main.py play generated/my_game` |
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
├── runtime/       # Game engine, lorebook, agent loop
├── web/           # Flask server + frontend
├── generated/     # Compiled SKILL output (gitignored)
├── samples/       # Example world books
└── start.bat      # Launcher
```

## Requirements

- Python 3.12+
- httpx, jinja2, flask (auto-installed)
- An OpenAI-compatible API (DeepSeek, OpenAI, etc.)

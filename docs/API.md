# TRPG2SKILL API 参考

Base URL: `http://127.0.0.1:8641`

## compile `/api/compile`

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/start` | `{world_book_text, output_name?, feedback?}` | SSE stream |

## play `/api/play`

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| POST | `/load` | `{game_dir}` | `{ok, game_name, phase, turn, location, history}` |
| POST | `/narrate` | — | `{narrative, turn, day, phase, location, inventory, flags, waiting}` |
| POST | `/input` | `{text}` | `{narrative, turn, day, phase, location, waiting}` |
| GET | `/state` | — | `{turn, day, phase, location, inventory, flags, npcs, custom, state_fields}` |
| POST | `/reset` | — | `{ok, game_name}` |
| POST | `/command` | `{cmd}` | `{ok, changed}` for `/hotreload` |
| GET | `/list` | — | `{skills: [{name, path, dir, loadable, turn?, phase?}]}` |
| POST | `/add` | `{path}` | `{ok, path}` |
| POST | `/scan` | `{dir}` | `{skills, scanned_path}` |

## config `/api/config`

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| GET | `/profiles` | — | `{profiles, active}` |
| POST | `/profiles` | `{name, base_url, api_key, model, ...}` | `{ok}` |
| POST | `/profiles/activate` | `{name}` | `{ok}` |
| POST | `/profiles/delete` | `{name}` | `{ok}` |
| GET | `/test` | — | `{ok, model, latency_ms, response}` |
| GET | `/game` | — | `{fields}` (needs active game) |
| POST | `/game/update` | `{key, value}` | `{ok}` |
| POST | `/game/reset` | — | `{ok}` |

## save `/api/save`

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| GET | `/slots` | `?dir=` (optional) | `{slots: [{name, turn, day, phase, ...}]}` |
| POST | `/manual` | `{name?}` | `{ok, name}` |
| POST | `/load/<name>` | — | `{ok, turn, phase, location, history}` |
| DELETE | `/<name>` | — | `{ok}` |

## lorebook `/api/lorebook`

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| GET | `/entries` | — | `{entries}` |
| GET | `/active` | — | `{active}` |

## edit `/api/edit`

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| GET | `/bans` | `?dir=` | `{bans}` |
| POST | `/bans` | `{dir, bans}` | `{ok}` |
| POST | `/bans/smart-dedup` | `{dir}` | `{bans}` |
| GET | `/lorebook` | `?dir=` | `{entries}` |
| POST | `/lorebook` | `{dir, entries}` | `{ok}` |
| GET | `/tool-pool` | `?dir=&tool=` | `{pool}` |
| POST | `/tool-pool` | `{dir, tool, pool}` | `{ok}` |
| GET | `/agents` | `?dir=` | `{text}` |
| POST | `/agents` | `{dir, text}` | `{ok}` |

---

## 错误响应格式

所有端点返回 `{"error": "<message>"}` 并附带适当的 HTTP 状态码：
- `400` — 请求参数错误
- `403` — 路径越权
- `404` — 资源不存在
- `500` — 内部错误

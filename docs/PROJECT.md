# Project Overview: Claude the Gardener

An autonomous plant-care system where a Claude Code agent runs every 15 minutes on a Raspberry Pi, reads soil moisture from an ESP32 sensor, decides whether to water or adjust lighting, and publishes a live public dashboard at [plants.cynexia.com](https://plants.cynexia.com).

---

## Architecture: Two Independent Loops

The system has two distinct loops that share **Cloudflare R2** as their only coupling point.

```
┌─ Live control loop (real-time, on Pi) ────────────────────────┐
│                                                                 │
│   ESP32 (M5Stack) ←─HTTP─→ MCP Server (app/) ←─MCP─→ Agent   │
│   gardener-esp32.local:80     0.0.0.0:8000/mcp                │
│   Home Assistant  ←─HTTP─┘  (grow light control only)         │
│                                                                 │
│   Agent writes: app/data/*.jsonl, app/photos/                  │
└─────────────────────────────────────────────────────────────────┘
              ↓ (pi/sync-to-r2.sh every 15 min)

         Cloudflare R2  ←── boundary ──→  GitHub Actions

┌─ History pipeline (async, in GHA) ────────────────────────────┐
│                                                                 │
│   R2: raw/data/, raw/sessions/, gardener-photos/               │
│        ↓ (process.yml every 15 min)                            │
│   gha-processor → R2: state/*.json, state/day/YYYY-MM-DD.json  │
│        ↓ (build.yml every 15 min)                              │
│   Astro site build → Cloudflare Workers → plants.cynexia.com   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Cross-cutting: healthchecks.io (host-monitor, agent, app)
```

**Important:** The public site is never real-time. Data takes up to ~30 minutes to flow from Pi → R2 → processed state → built site → deployed.

---

## Module Directory

| Directory | Role | Language | Entry point |
|-----------|------|----------|-------------|
| `app/` | MCP server exposing plant tools + web UI | Python 3.13 / FastMCP / Uvicorn | `app/server.py`, `app/run_http.py` |
| `agent/` | Autonomous Claude Code agent deployment | Shell / Claude CLI | `agent/deploy/run-agent.sh` |
| `esp32/` | Firmware: HTTP REST API for sensor + pump | C++ / Arduino | `esp32/gardener-controller/gardener-controller.ino` |
| `pi/` | Incremental R2 sync (data, photos, notes) | Shell / rclone | `pi/sync-to-r2.sh` |
| `gha-processor/` | Incremental R2 data → structured JSON state | Python 3.13 / boto3 | `gha-processor/processor/main.py` |
| `site/` | Public Astro dashboard | TypeScript / Astro 5.x / Tailwind v4 | `site/src/pages/index.astro` |
| `host-monitor/` | Pi host liveness ping to healthchecks.io | Shell / systemd | `host-monitor/host-healthcheck.service` |
| `static_site_generator/` | **DEAD CODE — do not modify** | Python / Jinja2 | *(not invoked by any CI workflow)* |
| `gha-processor/scripts/` | Shared install helpers (shell functions) | Shell | `gha-processor/scripts/install-helpers.sh` |
| `.github/workflows/` | CI/CD: `process.yml` + `build.yml` | GitHub Actions | — |

---

## Data Flows

### R2 Bucket: `gardener-data`
- **Written by:** `pi/sync-to-r2.sh` (rclone)
- **Read by:** `gha-processor`
- **Paths:**
  - `raw/data/plant_YYYYMMDD_HHMMSS.jsonl` — sensor readings, actions, messages
  - `raw/sessions/` — Claude session JSONL files (token usage, cost)
  - `raw/notes/` — versioned notes archive (separate from main sync)
  - `state/` — **written by gha-processor**, read by site build

### R2 Bucket: `gardener-photos`
- **Written by:** `pi/sync-to-r2.sh` → `YYYY/MM/DD/plant_YYYYMMDD_HHMMSS_mmm.jpg`
- **Read by:** `gha-processor` (photo selection), `site` (CDN via `gardener-photos.cynexia.com`)

### State JSON (R2 `state/`)
Produced by `gha-processor`, consumed by the Astro build:

| File | Contents |
|------|----------|
| `state/current_state.json` | Latest plant status, moisture, last agent message |
| `state/day_index.json` | List of all days with data (for static path generation) |
| `state/day/YYYY-MM-DD.json` | Per-day sensor readings, photos, messages, AI usage |
| `state/ai_stats.json` | Aggregate AI cost by day/model |
| `state/conversation.json` | Full agent-human message history |
| `state/sensor_stats_daily.json` | Daily moisture/light aggregates |

---

## CI/CD Workflows

### `process.yml` — Data Processor
- **Schedule:** every 15 minutes
- **Does:** runs `gha-processor` → reads R2 raw/ → writes R2 state/
- **Concurrency:** `cancel-in-progress: false` (never interrupt a running processor)
- **Timeout:** 25 minutes

### `build.yml` — Site Builder
- **Schedule:** every 15 minutes
- **Does:** downloads R2 state/ → `npm run build` on `site/` → deploys to Cloudflare Workers
- **Concurrency:** `cancel-in-progress: true` (only latest build matters)
- **No deploy gate** — the workflow fetches `current_state.json` and logs `last_run` but does not gate the build on it; always rebuilds

---

## MCP Server Tools (app/)

The agent interacts exclusively through these MCP tools:

**Plant status**
| Tool | What it does |
|------|-------------|
| `write_plant_status` | **Must be called first each cycle** (gatekeeper) |
| `get_current_plant_status` | Returns status written this cycle (does not re-read sensors) |
| `get_plant_status_history` | Recent status records from JSONL |

**Moisture**
| Tool | What it does |
|------|-------------|
| `read_moisture` | Live HTTP GET to ESP32 `/moisture` |
| `get_moisture_history` | Recent readings from JSONL (time-bucketed) |

**Watering**
| Tool | What it does |
|------|-------------|
| `dispense_water` | HTTP POST to ESP32 `/pump` (10–25 ml per call; 500 ml/24h cap) |
| `get_water_usage_24h` | Check ml used and remaining in current 24h window |
| `get_water_history` | Recent watering events from JSONL |

**Grow light** (via Home Assistant, not ESP32)
| Tool | What it does |
|------|-------------|
| `turn_on_light` | Activate light via HA REST API (30–120 min; ≥30 min cool-down) |
| `turn_off_light` | Deactivate light via HA REST API |
| `get_light_status` | Real-time HA state; forces turn-off if auto-off time has elapsed |
| `get_light_history` | Recent light events from JSONL |

**Camera**
| Tool | What it does |
|------|-------------|
| `capture_photo` | USB webcam snapshot, saved to `app/photos/` |
| `get_recent_photos` | URLs of recently captured photos |
| `get_camera_status` | Camera availability and config |
| `get_camera_history_bucketed` | Camera usage over time |

**Thinking / reasoning log**
| Tool | What it does |
|------|-------------|
| `log_thought` | Save reasoning to JSONL |
| `get_recent_thoughts` | Recent thought entries |
| `get_thoughts_in_range` | Thoughts within a time range |
| `search_thoughts` | Keyword search in recent thoughts |
| `get_thought_history_bucketed` | Thought activity over time |

**Action log**
| Tool | What it does |
|------|-------------|
| `log_action` | Record an action to JSONL |
| `get_recent_actions` | Recent action entries |
| `search_actions` | Keyword search in recent actions |
| `get_action_history_bucketed` | Action activity over time |

**Messaging**
| Tool | What it does |
|------|-------------|
| `send_message_to_human` | Write to JSONL + optional SMTP email |
| `list_messages_from_human` | Read human replies from JSONL |

**Notes (persistent memory)**
| Tool | What it does |
|------|-------------|
| `save_notes` | Overwrite `notes.md`; archives prior version automatically |
| `fetch_notes` | Read current `notes.md` |

**Utility**
| Tool | What it does |
|------|-------------|
| `get_current_time` | Current UTC time |

---

## Web UI (app/ — local Pi only)

In addition to the MCP endpoint, `app/run_http.py` serves a local Starlette web UI on the Pi (port 8000). This is for human use on the local network — not the public site.

| Route | Purpose |
|-------|---------|
| `GET /gallery` | Photo gallery browser |
| `GET /api/photos` | Recent photos as JSON |
| `POST /api/capture` | Trigger a photo capture |
| `GET /messages` | Human-agent message inbox UI |
| `GET /api/messages` | Messages as JSON |
| `POST /api/messages/reply` | Submit a reply to the agent |
| `POST /admin/reset-cycle` | Release the agent cycle gate (called by systemd ExecStopPost) |

The web UI and the MCP server share the same process — `run_http.py` mounts both the FastMCP app and the Starlette routes under Uvicorn.

---

## Key Business Rules

### Agent cycle
- `write_plant_status` must be called **before any actuator tool** — it sets the cycle gate
- Agent run is locked by `flock` to prevent concurrent runs
- `ExecStopPost` in the systemd service calls `/admin/reset-cycle` to release the gate after each run
- Claude session history retained for 1000 days (`cleanupPeriodDays`)

### Watering
- Daily cap: **500 ml / 24 hours** (enforced in `app/tools/water_pump.py`)
- Per-dispense bounds: **10–25 ml**
- Pump hard limit: **30 seconds** (ESP32 enforces this independently)
- ESP32 rejects concurrent pump requests with HTTP 409

### Grow light
- Duration bounds: **30–120 minutes**
- Cool-down: **≥30 minutes** between activations
- Auto-off is scheduled via asyncio task; on crash, `get_light_status` forces turn-off if scheduled_off has elapsed

### Photo selection (gha-processor)
- Only photos taken while the grow light was on are selected for display
- If no light data exists for a day → empty photo set (no fallback to dark photos)
- Up to **6 photos per day** in 4-hour windows; "noon" = slot nearest **14:00 UTC**

### Incremental processing (gha-processor)
- Watermark-based: cursor written **last** (replay-safe on failure)
- Conversation is **always rebuilt from scratch** (no watermark)

### Site build
- Static paths for day pages generated **only** from `day_index.json`
- "NO RECORD" placeholder shown if a day JSON is missing
- Stats chart switches from hourly to daily resolution at **7-day threshold**

---

## Health Monitoring

Three separate healthchecks.io monitors distinguish failure modes:

| Monitor | Source | Interval | Purpose |
|---------|--------|----------|---------|
| Host liveness | `host-monitor/` systemd timer | 15 seconds | Is the Pi reachable? |
| Agent execution | `agent/deploy/run-agent.sh` | Every agent run | Did the agent run and succeed? |
| MCP server | `app/run_http.py` background loop | Configurable | Is the MCP server up? |

URLs are never committed — substituted at install time by `install-agent.sh` / `install-sync.sh`.

---

## Dead Code

| Module | Status |
|--------|--------|
| `static_site_generator/` | Fully superseded by `gha-processor` + `site`. Not referenced by any CI workflow. Safe to ignore entirely. |

---

## ESP32 Hardware

- **Board:** M5Stack CoreS3-SE (ESP32-S3)
- **mDNS:** `gardener-esp32.local`
- **API:**
  - `GET /moisture` — raw ADC + calibrated reading
  - `POST /pump` — body `{"duration_seconds": N}` (1–30)
  - `GET /status` — firmware info, pump/moisture state
- **First boot:** WiFiManager captive portal for WiFi provisioning
- **OTA:** supported
- Moisture calibration constants: wet ≈ 1100, dry ≈ 3400 (documented, not enforced — left to agent reasoning)

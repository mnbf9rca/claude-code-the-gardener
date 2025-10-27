# Claude the Gardener - Static Site Generator

A static site generator that transforms Claude's autonomous plant care journey into an interactive HTML website.

## Features

- **Dashboard** - Overview stats, current plant status, recent activity
- **Conversations** - Browse all 224+ conversations with filtering and search
- **Timeline** - Unified timeline of all events (actions, thoughts, sensors, photos)
- **Sensors** - Interactive charts for moisture, light, and water data
- **Photos** - Gallery of all plant photos taken
- **Notes** - Evolution of Claude's understanding over time
- **Annotations** - Add your own notes to any event (stored locally)

## Quick Start

**Note:** This is part of a monorepo. All commands should be run from the `static_site_generator/` directory.

### 1. Sync Data from Raspberry Pi

```bash
cd static_site_generator
./sync_data.sh
```

This will:
- Connect to your Raspberry Pi (rob@192.168.17.145 by default)
- Sync MCP server data from `/home/mcpserver/data/`
- Sync Claude conversations from `/home/gardener/.claude/`
- Sync plant photos from `/home/mcpserver/photos/`
- Download to `../app/data/` and `../app/photos/`

**Tip:** Use `./sync_data.sh --dry-run` to preview changes first.

### 2. Generate the Static Site

```bash
uv run python generate.py
```

This will:
- Parse all JSONL files (conversations, sensors, actions, thoughts)
- Calculate statistics and trends
- Generate HTML pages with Jinja2 templates
- Export JSON data for JavaScript charts
- Copy photos to output directory
- Output to `./output/`

**Note:** Uses `uv` for dependency management. The first run will create a virtual environment.

### 3. View the Site

**Option A - Direct file access:**
```bash
open output/index.html
```

**Option B - Local web server:**
```bash
uv run python -m http.server -d output 8080
# Visit http://localhost:8080
```

## Configuration

Edit `sync_data.sh` to change:
- `DEFAULT_SOURCE_HOST` - Raspberry Pi hostname/IP
- `SOURCE_DATA_PATH` - Path to MCP data on Pi
- `SOURCE_CLAUDE_PATH` - Path to Claude conversations on Pi
- `LOCAL_DATA_DIR` - Where to sync data locally

## Project Structure

```
static_site_generator/
├── pyproject.toml           # Python dependencies (uv)
├── generate.py              # Main generator script (with CLI args)
├── sync_data.sh             # Data sync script
├── publish.sh               # S3 publishing with change detection
├── orchestrate.sh           # Pipeline orchestrator
├── .env.publish.example     # Template for AWS credentials
├── .gitignore               # Ignore output/.git and secrets
├── parsers/                 # Data parsing modules
│   ├── stats.py             # Overall statistics
│   ├── conversations.py     # Conversation parsing & rendering
│   ├── sensors.py           # Sensor data processing
│   ├── actions.py           # Timeline and actions
│   ├── tool_formatters.py  # Tool input/result formatters (registry)
│   └── formatting_utils.py # Shared HTML formatting utilities
├── templates/               # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── conversations.html
│   ├── conversation_detail.html
│   ├── timeline.html
│   ├── sensors.html
│   ├── photos.html
│   └── notes.html
├── static/                  # CSS, JavaScript
│   ├── css/style.css
│   └── js/
│       ├── time-utils.js        # Shared time parsing utilities
│       ├── charts.js            # Chart.js visualizations
│       ├── date-filter.js       # Date filtering logic
│       ├── annotations.js       # Annotation system
│       └── timeline.js          # Timeline rendering
├── deploy/                  # Deployment files for Raspberry Pi
│   ├── install-publisher.sh             # Installation script
│   ├── gardener-site-publisher.service  # Systemd service
│   └── gardener-site-publisher.timer    # Systemd timer
├── docs/                    # Documentation
│   ├── S3_SETUP.md          # S3 bucket configuration guide
│   └── PUBLISHING.md        # Publishing workflow guide
├── .venv/                   # Virtual environment (created by uv)
└── output/                  # Generated site (gitignored)
    ├── .git/                # Git repo for change tracking (gitignored)
    ├── index.html
    ├── conversations/
    ├── photos/
    ├── data/                # JSON for JavaScript
    └── static/
```

## Data Sources

The generator parses these JSONL files from `../app/data/`:

- `claude/*.jsonl` - All conversation transcripts (224+ files)
- `moisture_sensor_history.jsonl` - Soil moisture readings
- `light_history.jsonl` - Light activation events
- `water_pump_history.jsonl` - Water dispensing events
- `action_log.jsonl` - All actions taken
- `thinking.jsonl` - Claude's thought process
- `camera_usage.jsonl` - Photo metadata
- `messages_to_human.jsonl` - Messages sent to you
- `messages_from_human.jsonl` - Your messages to Claude
- `notes.md` - Current notes
- `notes_archive/*.md` - Historical notes versions

## Output

The generated site includes:

- **224+ conversation detail pages** - Full message history with tool calls
- **Interactive charts** - Chart.js visualizations of sensor data
- **Searchable timeline** - Filter by event type (water, light, thought, etc.)
- **Photo gallery** - All plant photos with timestamps
- **Statistics dashboard** - Token usage, costs, activity metrics
- **Annotation system** - Add notes to any event (stored in localStorage)

## Publishing to AWS S3

This project includes automated publishing to AWS S3 with change detection.

### Quick Start (Local Machine)

**Prerequisites:** AWS CLI installed (`brew install awscli` on macOS)

```bash
# 1. Set up environment file
cp .env.publish.example .env.publish
# Edit and add your AWS credentials

# 2. Set up S3 bucket (one-time)
# See docs/S3_SETUP.md for detailed instructions

# 3. Run the complete pipeline
source .env.publish  # Load credentials
./orchestrate.sh --s3-bucket your-bucket-name
```

This will:
- Sync latest data from Pi
- Generate fresh HTML
- Upload to S3 (only if changes detected)

### Automated Publishing (Raspberry Pi)

Deploy the publisher to run automatically every 15 minutes:

```bash
# 1. Install the publisher on Pi (installs AWS CLI, Python deps, systemd units)
sudo bash deploy/install-publisher.sh

# 2. Edit .env.publish with your AWS credentials
sudo nano /home/mcpserver/gardener-publisher/.env.publish

# 3. Enable the timer
sudo systemctl enable --now gardener-site-publisher.timer

# 4. Monitor
journalctl -u gardener-site-publisher -f
```

**Note:** The install script automatically installs AWS CLI v2 if not present.

### Modular Scripts

The publishing system consists of three independent scripts:

1. **sync_data.sh** - Sync data from Raspberry Pi
   ```bash
   ./sync_data.sh [--dry-run]
   ```

2. **generate.py** - Build static site
   ```bash
   uv run python generate.py \
       [--data-dir <path>] \
       [--photos-dir <path>] \
       [--output-dir <path>]
   ```

3. **publish.sh** - Upload to S3 (with change detection)
   ```bash
   ./publish.sh \
       --output-dir <path> \
       --s3-bucket <name> \
       [--dry-run]
   ```

4. **orchestrate.sh** - Chain all three together
   ```bash
   ./orchestrate.sh \
       --s3-bucket <name> \
       [--skip-sync] \
       [--dry-run]
   ```

### Documentation

- **[S3_SETUP.md](docs/S3_SETUP.md)** - Complete S3 bucket configuration guide
- **[PUBLISHING.md](docs/PUBLISHING.md)** - Publishing workflow and deployment guide

### Change Detection

The publish script only uploads when changes are detected:
- Uses git in `output/` directory to track changes
- Runs `git diff` before uploading
- Skips S3 upload if no changes (saves money!)
- Commits after successful publish (audit trail)

### Other Deployment Options

The `output/` directory is a standard static site. You can also deploy to:

- **GitHub Pages**: Push `output/*` to `gh-pages` branch
- **Netlify/Vercel**: Drag and drop the `output/` folder
- **Any static host**: Just upload the files!

## Development

**Requirements:**
- Python 3.13+ (specified in `pyproject.toml`)
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [AWS CLI](https://aws.amazon.com/cli/) - For S3 publishing
- SSH access to Raspberry Pi (for syncing)

**Dependencies** (managed by `uv` via `pyproject.toml`):
- Jinja2 >= 3.1.0
- markdown2 >= 2.5.0

**Regenerate after data updates:**
```bash
./sync_data.sh        # Fetch latest data
uv run python generate.py  # Regenerate site
```

## Tips

- **First time?** Start with `./sync_data.sh --dry-run` to test connection
- **Slow generation?** The script limits conversation detail pages to avoid memory issues
- **Custom annotations?** Click "+ Add Note" on any timeline event
- **Export annotations?** Run `window.gardenerAnnotations.export()` in browser console
- **Missing photos?** Check that `../app/photos/` exists and contains `plant_*.jpg` files

## Highlights Detection

The generator automatically detects interesting moments:
- First water dispensed
- High token usage conversations (>50K tokens)
- Many tool calls (>20 per conversation)
- Messages to/from human
- Repeated concerns (same tag appearing 5+ times)

## KISS Philosophy

This generator follows the Keep It Simple, Stupid principle:
- ✅ Plain HTML + CSS + vanilla JS (no build tools)
- ✅ Static JSON files (no database)
- ✅ Client-side filtering (no backend)
- ✅ CDN for Chart.js (no npm)
- ✅ localStorage for annotations (no server)

## Troubleshooting

**"Data directory not found"**
- Run `./sync_data.sh` first to download data from Pi

**"Cannot connect to host"**
- Check Pi is on and SSH is enabled
- Verify hostname/IP in `sync_data.sh`
- Ensure SSH keys are set up

**Charts not showing**
- Check browser console for errors
- Verify `output/data/sensor_data.json` exists
- Ensure Chart.js CDN is accessible

**Photos not appearing**
- Check `../app/photos/` contains images
- Verify filenames match pattern `plant_*.jpg`

## License

Part of the Claude Code the Gardener project. See main repository for license.

## Contributing

This is a hobby project! Feel free to fork and customize for your own use.

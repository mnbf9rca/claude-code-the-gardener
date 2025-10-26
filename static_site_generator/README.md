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

### 1. Sync Data from Raspberry Pi

```bash
cd static_site_generator
./sync_data.sh
```

This will:
- Connect to your Raspberry Pi (rob@192.168.17.145 by default)
- Sync MCP server data from `/home/mcpserver/data/`
- Sync Claude conversations from `/home/gardener/.claude/`
- Download to `../app/data/`

**Tip:** Use `./sync_data.sh --dry-run` to preview changes first.

### 2. Generate the Static Site

```bash
python generate.py
```

This will:
- Parse all JSONL files (conversations, sensors, actions, thoughts)
- Calculate statistics and trends
- Generate HTML pages with Jinja2 templates
- Export JSON data for JavaScript charts
- Copy photos to output directory
- Output to `./output/`

### 3. View the Site

**Option A - Direct file access:**
```bash
open output/index.html
```

**Option B - Local web server:**
```bash
python -m http.server -d output 8080
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
├── generate.py           # Main generator script
├── sync_data.sh          # Data sync script
├── parsers/              # Data parsing modules
│   ├── stats.py          # Overall statistics
│   ├── conversations.py  # Conversation parsing
│   ├── sensors.py        # Sensor data processing
│   └── actions.py        # Timeline and actions
├── templates/            # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── conversations.html
│   ├── conversation_detail.html
│   ├── timeline.html
│   ├── sensors.html
│   ├── photos.html
│   └── notes.html
├── static/               # CSS, JavaScript
│   ├── css/style.css
│   └── js/
│       ├── charts.js
│       ├── annotations.js
│       └── timeline.js
└── output/               # Generated site (gitignored)
    ├── index.html
    ├── conversations/
    ├── photos/
    ├── data/             # JSON for JavaScript
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

## Deployment

The `output/` directory contains a complete static site. Deploy to:

- **GitHub Pages**: Push `output/*` to `gh-pages` branch
- **AWS S3**: `aws s3 sync output/ s3://your-bucket --acl public-read`
- **Netlify/Vercel**: Drag and drop the `output/` folder
- **Any static host**: Just upload the files!

## Development

**Requirements:**
- Python 3.8+
- Jinja2: `pip install jinja2`
- SSH access to Raspberry Pi (for syncing)

**Regenerate after data updates:**
```bash
./sync_data.sh  # Fetch latest data
python generate.py  # Regenerate site
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

# Claude the Gardener - Static Site Generator

> **MIGRATED TO GITHUB CI** (2026-02-06)
>
> This site now builds automatically via GitHub Actions when data is pushed to the `mnbf9rca/gardener-site` repository. The Raspberry Pi no longer generates or publishes the site directly - it only pushes raw data to GitHub every 15 minutes.
>
> See [Migration Design](../docs/plans/2026-02-06-astro-github-ci-migration-design.md) for details.

---

## Architecture (New)

### Raspberry Pi User Architecture

**Multi-user setup for security and isolation:**

- **`gardener`** - Runs Claude Code only
  - Isolated: Cannot access hardware/sensors directly
  - Stores conversations in `~/.claude/projects/`
- **`mcpserver`** - Runs MCP server with hardware access
  - Isolated: Cannot run arbitrary code
  - Stores sensor data in `~/data/` and `~/photos/`
- **`gardener-publisher`** - NEW ROLE: Syncs data to GitHub
  - Previously: Generated HTML locally and published to S3 with AWS credentials
  - Now: Only pushes raw data to GitHub (no AWS credentials needed)
  - Has group read access to `mcpserver` and `gardener` data
  - Runs systemd timer every 15 minutes

### Two-Repository Strategy

1. **gardener-site** (data + CI) - Raw JSONL, photos, logs pushed by Pi every 15 minutes + GitHub Actions workflow
2. **claude-code-the-gardener** (code) - Python parsers + Astro site

### Data Flow Pipeline

```
Pi (gardener-publisher user):
  - Syncs from /home/mcpserver/data → gardener-site/data/
  - Syncs from /home/mcpserver/photos → gardener-site/photos/
  - Syncs from /home/gardener/.claude/ → gardener-site/data/claude/
  - Pushes to GitHub every 15 min

GitHub Actions (on push to gardener-site):
  - Checkouts claude-code-the-gardener (code repo)
  - Runs Python parsers to generate JSON
  - Builds Astro static site
  - Deploys to S3 + invalidates CloudFront
```

### Why This Change?

**Before:** `gardener-publisher` generated HTML locally and pushed to S3 with AWS credentials

**After:** `gardener-publisher` only pushes raw data to GitHub; CI does the rest

**Benefits:**
- No AWS credentials on Pi (uses GitHub OIDC in CI)
- Centralized deployment via GitHub Actions
- All historical data preserved in git
- Better for future UX iterations with Astro
- Automatic rebuilds on data updates

## Quick Start (Local Development)

### 1. Clone Both Repositories

```bash
# Clone data repo
git clone https://github.com/mnbf9rca/gardener-site.git

# Clone code repo
git clone https://github.com/mnbf9rca/claude-code-the-gardener.git
cd claude-code-the-gardener/static_site_generator
```

### 2. Generate Data Files

```bash
uv run python scripts/generate-data.py \
  --data-dir ../../gardener-site/data \
  --photos-dir ../../gardener-site/photos \
  --output-dir ./public/data
```

### 3. Run Astro Dev Server

```bash
npm install
npm run dev
```

Visit http://localhost:4321

### 4. Build for Production

```bash
npm run build
```

Output in `dist/` directory

## Raspberry Pi Setup

### Prerequisites

The Pi must already have these users configured:
- `gardener` - Running Claude Code
- `mcpserver` - Running MCP server with data in `/home/mcpserver/{data,photos}`
- `gardener-publisher` - Has group access to both users (set up by install-publisher.sh)

### Fresh Install (No Old Publisher)

If you've never run the old publisher system:

```bash
# From the claude-code-the-gardener repo
sudo bash static_site_generator/deploy/install-data-sync.sh
```

This will:
1. Clone `gardener-site` repo to `/home/gardener-publisher/gardener-site`
2. Generate SSH key for GitHub (you'll add it to GitHub Settings > SSH Keys)
3. Create push script that syncs data every 15 minutes
4. Install systemd timer to run as `gardener-publisher` user

### Migrate from Old Publisher

If the old publisher is currently running:

```bash
sudo bash static_site_generator/deploy/migrate-to-github.sh --dry-run  # Preview
sudo bash static_site_generator/deploy/migrate-to-github.sh            # Execute
```

This will:
1. Backup old `.env.publish` from `/home/gardener-publisher/app/`
2. Stop old `gardener-site-publisher.timer`
3. Run the installation script above

### Monitor

```bash
# Watch sync logs
journalctl -u gardener-data-sync -f

# Check timer status
systemctl status gardener-data-sync.timer

# Trigger manual sync
sudo systemctl start gardener-data-sync.service
```

## Project Structure

```
static_site_generator/
├── scripts/
│   └── generate-data.py      # Orchestrates parsers to generate JSON
├── parsers/                   # Python parsers for JSONL data
│   ├── stats.py              # Overall statistics
│   ├── conversations.py       # Claude conversation logs
│   ├── sensors.py            # Sensor time-series data
│   └── actions.py            # Timeline events
├── src/
│   ├── layouts/              # Astro layouts
│   ├── pages/                # Astro pages (routes)
│   ├── components/           # Reusable components
│   └── styles/               # Global styles
├── public/
│   ├── data/                 # Generated JSON files (git-ignored)
│   └── styles/               # Public CSS
└── deploy/                   # Raspberry Pi deployment scripts
```

## Commands

| Command                   | Action                                           |
| :------------------------ | :----------------------------------------------- |
| `npm install`             | Installs dependencies                            |
| `npm run dev`             | Starts local dev server at `localhost:4321`      |
| `npm run build`           | Build your production site to `./dist/`          |
| `npm run preview`         | Preview your build locally, before deploying     |

## Related Repositories

- Data: [gardener-site](https://github.com/mnbf9rca/gardener-site)
- Live site: https://plants.cynexia.com

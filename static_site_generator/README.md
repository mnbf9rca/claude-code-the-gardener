# Claude the Gardener - Static Site Generator

> **MIGRATED TO GITHUB CI** (2026-02-06)
>
> This site now builds automatically via GitHub Actions when data is pushed to the `mnbf9rca/gardener-site` repository. The Raspberry Pi no longer generates or publishes the site directly - it only pushes raw data to GitHub every 15 minutes.
>
> See [Migration Design](../docs/plans/2026-02-06-astro-github-ci-migration-design.md) for details.

---

## Architecture (New)

**Two-Repository Strategy:**

1. **gardener-site** (data + CI) - Raw JSONL, photos, logs pushed by Pi every 15 minutes + GitHub Actions workflow
2. **claude-code-the-gardener** (code) - Python parsers + Astro site

**Pipeline:**
```
Pi → Push data to gardener-site → GitHub Actions triggers →
  Checkout code repo → Run Python parsers → Build Astro →
  Deploy to S3 → Invalidate CloudFront
```

**Why this change?**
- Simpler Pi setup (no AWS credentials needed)
- Centralized deployment via CI
- Better for future UX iterations with Astro
- All historical data archived in git
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

**Fresh Install:**

```bash
sudo bash deploy/install-data-sync.sh
```

**Migrate from Old System:**

```bash
sudo bash deploy/migrate-to-github.sh --dry-run  # Preview
sudo bash deploy/migrate-to-github.sh            # Execute
```

**Monitor:**

```bash
journalctl -u gardener-data-sync -f
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

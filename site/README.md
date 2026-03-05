# Claude the Gardener — Monitoring Dashboard

Static Astro 5 site serving as the monitoring dashboard for Claude the Gardener, an autonomous plant-care AI agent. Deployed at [plants.cynexia.com](https://plants.cynexia.com).

## Pages

| Route | Description |
| :---- | :---------- |
| `/` | Dashboard — live status overview |
| `/grid` | Plant Grid — photo thumbnails per plant |
| `/day/[date]` | Day Detail — full log for a given date |
| `/conversation` | Conversation — Claude's recent reasoning and actions |
| `/stats` | Stats — sensor history charts |
| `/about` | About — project overview |

## Data

State files live in `src/data/state/` as JSON. They are **not committed to the repo** (`.gitignore`). At build time, GitHub Actions fetches them from Cloudflare R2 via `rclone`.

## Local Development

You need the state files before the dev server is useful. Fetch them manually or with `rclone`:

```sh
rclone copy r2:your-bucket/state site/src/data/state/
npm install
npm run dev        # http://localhost:4321
```

## Build & Deploy

```sh
npm run build      # outputs to ./dist/
```

Deployment to Cloudflare Pages is handled automatically by GitHub Actions on every push to `main`. No manual deploy step is required.

## Theme

"Amber Phosphor Herbarium" — dark terminal aesthetic with amber/green accents.

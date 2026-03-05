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

State files live in `src/data/state/` as JSON. They are **not committed to the repo** (`.gitignore`). At build time, GitHub Actions fetches them from Cloudflare R2 via the AWS CLI (S3-compatible endpoint).

## Local Development

You need the state files before the dev server is useful. Set the required env vars (obtain values from project settings):

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `R2_ENDPOINT_URL`
- `R2_BUCKET_NAME`

> **Note:** In the GitHub Actions project these are stored as `R2_ACCESS_KEY_ID` (→ `AWS_ACCESS_KEY_ID`) and `R2_SECRET_ACCESS_KEY` (→ `AWS_SECRET_ACCESS_KEY`). `R2_ENDPOINT_URL` and `R2_BUCKET_NAME` use the same names in both places.

Sync state data from R2:

```sh
aws s3 sync \
  --endpoint-url "$R2_ENDPOINT_URL" \
  "s3://${R2_BUCKET_NAME}/state/" \
  site/src/data/state/ \
  --exclude "summaries/*"
```

Then start the dev server:

```sh
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

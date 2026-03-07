# The Pipeline Behind the Plant
*How Claude the Gardener's data infrastructure works*

## The Setup

An autonomous AI agent on a Raspberry Pi keeps a houseplant alive. Every 15 minutes it wakes, reads the soil moisture sensor, checks a photo, decides whether to water, runs the grow light schedule, and writes a journal entry. Then the cycle resets. It has been doing this for months.

After several months of continuous operation, the data store holds over 110,000 files: sensor readings in JSONL format, Claude session exports, and photos. A monitoring site at [plants.cynexia.com](https://plants.cynexia.com) rebuilds every 30 minutes. Build time: 2 to 5 minutes.

This is how the pipeline works.

## Four Layers, Four Jobs

The system has five components with a clean hierarchy: Raspberry Pi, Cloudflare R2, a GHA processor, a GHA builder, and Cloudflare Workers.

The Pi is a dumb pusher. It reads sensors, runs the Claude agent, and syncs files to R2 every 15 minutes via `pi/sync-to-r2.sh`. It does not transform, aggregate, or interpret. It appends.

R2 is the source of truth. Everything raw lands under `raw/` in the `gardener-data` bucket, organized by file mtime into `raw/sessions/YYYY/MM/DD/filename` and `raw/data/`. A second public bucket, `gardener-photos`, holds photos served via a custom domain. R2 is append-only by convention: the Pi never deletes from it.

The GHA processor runs every 30 minutes via `process.yml`. It reads from `raw/`, computes aggregated JSON state files, and writes them to `state/`. It does not touch `raw/`.

The GHA builder runs every 30 minutes via `build.yml`. It downloads the `state/` files from R2, injects them into an Astro static site, builds, and deploys to Cloudflare Workers. It does not touch `raw/` or rerun the processor.

The constraint that makes recovery mechanical: the Pi writes to `raw/`. GHA reads from `raw/` and writes to `state/`. Neither crosses that line.

## The Cursor

The most technically interesting piece is `state/current_state.json`, which serves as a processing bookmark for every data source.

At the start of each processor run, `load_cursor()` reads this file and fills in any missing watermarks with Unix epoch:

```python
wm.setdefault("sessions_last_modified", EPOCH)
wm.setdefault("photos_last_modified", EPOCH)
wm.setdefault("notes_last_modified", EPOCH)

sensor_wm = wm.setdefault("sensor_files", {})
for fname in SENSOR_FILES:
    sensor_wm.setdefault(fname, EPOCH)
```

If `current_state.json` doesn't exist, every watermark defaults to `1970-01-01T00:00:00Z`. The processor sees everything as new and does a full reprocess. That is the intended behavior for a first run or a deliberate reset.

On a normal run, the processor checks each watermark before pulling data. For session files, it lists R2 objects and filters to those with a `LastModified` timestamp newer than the watermark. For sensor JSONL files, it reads records and filters by the `timestamp` field in each line. Only new records get processed, then merged into existing aggregated state files: new days are added, old days are untouched.

The atomicity guarantee comes from where `save_cursor` is called. It is the final call in `main()`:

```python
def save_cursor(s3, bucket: str, state: dict) -> None:
    """Write updated cursor. Call this LAST — it commits the processing run."""
    state["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    put_json(s3, bucket, "state/current_state.json", state)
```

Every other state file, `ai_stats.json`, `sensor_stats_daily.json`, `plant_timeline.json`, `day_index.json`, the per-day detail files under `state/day/`, all get written before the cursor advances. If the process crashes mid-run, the next run replays from the same watermarks. Some state files may get written twice, but the merge logic is idempotent: new data overwrites same-date entries and old entries stay.

Build time before the cursor pattern: 45 to 60 minutes, eventually exceeding the 30-minute schedule. Build time after: 2 to 5 minutes. The processor now only examines records added since the last run, which is typically a handful of sensor readings and one or two photos.

## The Sync Script

`pi/sync-to-r2.sh` is around 140 lines of bash. The core of it is a loop over `find -newer` and a single rclone command:

```bash
rclone copyto \
    "$file" \
    "${REMOTE}:${dest_path}" \
    --log-level INFO \
    --stats-log-level DEBUG
```

Called in a loop over `find "$src" -type f -newer "$STATE_FILE" -not -path '*/.git/*'`. The state file at `~/.sync-state` is a sentinel touched at the end of each successful sync. `find -newer` gives every file modified since then.

`rclone copyto` is idempotent: if a file already exists at the destination with the same content, it is skipped. This means re-running the script after a partial failure is safe. No manifest required.

The one subtle piece is the timestamp ratchet. The script records the start time before any work begins:

```bash
SYNC_START=$(mktemp)
```

Then sets the state file to that timestamp at the end rather than the current time:

```bash
touch -r "$SYNC_START" "$STATE_FILE"
```

Files written to the Pi during the rclone phase, while uploads are in progress, are caught by the next run rather than silently dropped. The overlap is fine because `copyto` is idempotent.

## raw/ vs state/

Recovery from any failure is mechanical.

A `state/` file is corrupted or produced bad output? Delete it. The next GHA processor run rebuilds it from `raw/`. A new sensor type needs historical data backfilled? Set the relevant watermark back to epoch and let the processor replay. The processor logic changes and produces different aggregated output? Wipe all of `state/` and trigger a manual run.

`raw/` is append-only by convention. The Pi never deletes, and R2 has no lifecycle policy removing old files. Storage on R2 is cheap; the ability to replay from any point in history is not. `state/` is fully rebuildable from `raw/`, which makes it a cache. Treating a cache as a source of truth is how recovery becomes complicated. Here it never does.

At no point is there a state that cannot be recovered from without a backup. The Pi adds to `raw/`. GHA derives `state/` from `raw/`. If `state/` is wrong, delete it.

## What It Costs

Infrastructure runs around $6 per month: R2 storage and egress for both buckets, Cloudflare Workers for the site. GitHub Actions minutes for two 30-minute scheduled workflows fit comfortably in the free tier.

The Claude API cost is a different story. The daily average has settled at $41.46. Early in the project, on older and more expensive models, costs peaked above $180 per day on high-activity days. The agent runs 96 sessions per day around the clock. Each session involves multiple tool calls: reading the moisture sensor, checking the latest photo, deciding whether to water, writing a status note, updating the journal.

Infrastructure: $6/month. AI: $41/day. The server is nearly free. The model is the entire cost.

In systems built around AI capabilities, the natural instinct is to optimize infrastructure, because infrastructure costs are visible and familiar. Model costs arrive in the same invoice format, but they scale with decisions, not with uptime. Optimizing the wrong line item is easy to do and easy to miss.

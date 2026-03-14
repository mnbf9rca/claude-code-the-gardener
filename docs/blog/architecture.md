# Dumb edge, smart middle
*Building an autonomous plant monitor on Raspberry Pi + R2 + GitHub Actions*

## The problem

A Raspberry Pi runs Claude the Gardener, an autonomous AI agent whose job is to keep a houseplant alive. Every 15 minutes it wakes up, checks soil moisture, takes a photo, maybe waters the plant, and writes a journal entry. Then it does it again. For months.

After six months, the data store had grown to over 110,000 files: sensor readings, Claude session JSONL exports, and photos. Early on, the monitoring site rebuilt itself by reprocessing everything from scratch on every GitHub Actions run. Build times crept up to 45 to 60 minutes. That's a problem when you're running on a 30-minute schedule — you end up with a build queue that can never catch up.

The naive approach breaks down because it treats the pipeline like a batch job. Load everything, process everything, ship everything. That works for a one-time import. It doesn't work when the data keeps growing and your build budget is fixed.

The actual problem is simpler to state than it looks: how do you tell the system "only process what's new since last time" in a way that's fault-tolerant and idempotent, without a database?

## The architecture

The system has four layers, each with a single job.

The Raspberry Pi is a dumb pusher. It reads sensors, runs the Claude agent, and syncs data to Cloudflare R2 every 15 minutes. It does not transform or aggregate — it just appends. The sync script (`pi/sync-to-r2.sh`) is around 140 lines of bash that uses `rclone copyto` and `find -newer` to push only files changed since the last successful sync. Everything lands in `raw/`-prefixed paths organized by file mtime: `raw/sessions/YYYY/MM/DD/filename`. R2 is the append-only source of truth. The Pi never deletes from it.

GitHub Actions is the brain. The processor workflow (`process.yml`) runs every 30 minutes, pulls from R2, aggregates raw data into a handful of JSON state files, and writes those back to R2 under `state/`. A separate build workflow (`build.yml`) also runs every 30 minutes: it downloads the state files, injects them into an Astro static site, builds it, and deploys to Cloudflare Workers.

The design constraint that makes everything else work: the Pi and GHA never touch each other's data. The Pi writes to `raw/`. GHA reads from `raw/` and writes to `state/`. Neither crosses that line.

## The cursor pattern

The most technically interesting piece is the cursor in `state/current_state.json`.

Before each processing run, the processor loads this file and reads a `watermarks` block. Each watermark is an ISO 8601 timestamp for a specific data source — one for the sessions folder, one per sensor JSONL file, one for the photos bucket:

```python
wm.setdefault("sessions_last_modified", EPOCH)
wm.setdefault("photos_last_modified", EPOCH)
for fname in SENSOR_FILES:
    sensor_wm.setdefault(fname, EPOCH)
```

If the file doesn't exist — first run, or after deliberately deleting it — every watermark defaults to Unix epoch. The processor sees everything as new and does a full reprocess. That's the intended behavior.

During a normal run, the processor checks each watermark before pulling data. For sessions, it lists R2 objects and filters to those with a `LastModified` timestamp newer than the watermark. For sensor files, it reads records and filters by the `timestamp` field in each JSON line. Only new records get processed, then merged into existing aggregated state files: new days added, old days untouched.

The atomicity guarantee is in `cursor.py`:

```python
def save_cursor(s3, bucket: str, state: dict) -> None:
    """Write updated cursor. Call this LAST — it commits the processing run."""
    state["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    put_json(s3, bucket, "state/current_state.json", state)
```

`save_cursor` is the last call in `main()`. Every other state file — `ai_stats.json`, `sensor_stats_daily.json`, `plant_timeline.json`, the per-day detail files — gets written before the cursor advances. If the process crashes mid-run, the next run replays from the same watermarks. It may write some state files twice, but the merge logic is idempotent: new data overwrites same-date entries and old entries stay.

Build time: 45 to 60 minutes before. 2 to 5 minutes after. The processor now only looks at records added since the last run, which is typically a handful of sensor readings and a photo or two.

## Why rclone

The original sync implementation was about 600 lines of custom Python. It maintained a local manifest file, computed file hashes, generated JSONL delta logs for downstream consumers to parse, and handled partial failures by replaying from the manifest. It was, in retrospect, a small CDC (change data capture) system built from scratch for a problem that didn't need CDC.

The replacement is around 20 lines of bash:

```bash
rclone copyto \
    "$file" \
    "${REMOTE}:${dest_path}" \
    --log-level INFO \
    --stats-log-level DEBUG
```

Called in a loop over `find "$src" -type f -newer "$STATE_FILE"`. rclone's `copyto` is idempotent: if the file already exists at the destination with the same content, it's skipped. The state file (`~/.sync-state`) is a sentinel touched at the end of each successful sync. `find -newer` gives you everything since then.

The one subtle piece is the timestamp ratchet: the script records the start time before any work begins (`SYNC_START=$(mktemp)`), then sets the state file to that timestamp at the end rather than the current time. Files written to the Pi during the rclone phase are caught by the next run rather than silently dropped. The overlap doesn't matter because `copyto` is idempotent.

Reach for the right tool before writing the tool.

## raw/ vs state/

The Pi writes to `raw/` in R2 and never touches `state/`. GHA reads from `raw/`, computes, and writes to `state/`. It never modifies anything in `raw/`.

Recovery from any failure is mechanical. A `state/` file is corrupted? Delete it — the next GHA run rebuilds it from `raw/`. A new sensor type needs historical data backfilled? Set the relevant watermark back to epoch and let the processor replay. The processor logic changes and produces different output? Wipe all of `state/` and run again.

`raw/` is append-only by convention. The Pi never deletes, and R2 has no lifecycle policy removing old files. Disk space on R2 is cheap; the ability to replay from any point in history is worth more than the storage savings. `state/` is fully rebuildable, so it's a cache, not a source of truth.

At no point is there a state that can't be recovered from. The Pi adds to `raw/`. GHA derives `state/` from `raw/`. If `state/` is wrong, delete it. There's no third category of data that lives nowhere in particular and can only be recovered from backup. That's the constraint that makes everything else simple.

## Cost

Infrastructure runs around $6 per month: R2 storage and egress, plus Cloudflare Workers. GitHub Actions minutes for 30-minute scheduled workflows fit in the free tier.

The Claude API cost is a different story. The daily average has settled at $41.46. Early in the project, running on older and more expensive models, it peaked above $180 per day on high-activity days. The agent runs roughly every 15 minutes around the clock — 96 sessions per day — and each session involves multiple tool calls: reading sensors, checking photos, deciding whether to water, writing a status note.

Infrastructure: $6/month. AI: $41/day. The server is nearly free. The model is the entire cost. In AI-native systems, optimizing infrastructure while ignoring model efficiency is optimizing the wrong line item.

## What didn't work

The first attempt used Git as the state store. Each GHA run would commit updated state files to the repo; builds would read from Git instead of R2. This held for a week or two, then broke as data grew. Git isn't built for frequent automated commits to large data files — the repo history became noise, each commit diff was hundreds of kilobytes of JSON, and merge conflicts appeared whenever the build and process workflows ran simultaneously and both tried to push.

Before rclone, the sync script maintained a JSONL delta log alongside a manifest. Each sync event appended a line describing what changed; downstream consumers read the delta log to know what to process. The problem: the delta log needed its own management. It could grow without bound, had to be read in order, and any corruption in the middle broke everything downstream. It was reinventing a write-ahead log without the durability guarantees.

Both failures came from the same place: reaching for an abstraction built for a different problem. Git is for source code history. Delta logs are for database replication. What the system actually needed was a cursor in a JSON file and a storage layer with idempotent writes. R2 provides the storage. The cursor pattern provides the bookmark. Together they're around a hundred lines of code.

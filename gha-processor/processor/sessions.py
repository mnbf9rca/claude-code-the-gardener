"""Parse Claude session JSONL files and compute AI usage stats."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from processor.helpers import date_of, parse_ts
from processor.r2_client import get_jsonl_lines, list_objects


def load_pricing(pricing_path: str | Path | None = None) -> dict:
    """Load model_pricing.json. Defaults to the file next to this module."""
    if pricing_path is None:
        pricing_path = Path(__file__).parent / "model_pricing.json"
    with open(pricing_path) as f:
        return json.load(f)


def match_model_pricing(model_name: str, pricing: dict) -> dict:
    """Find pricing by longest-prefix match against the model name.

    e.g. "claude-sonnet-4-5-20250929" matches "claude-sonnet-4-5" (15 chars)
    over "claude-sonnet-4" (13 chars).
    """
    models = pricing["models"]
    best_key = None
    best_len = -1
    for key in models:
        if model_name.startswith(key) and len(key) > best_len:
            best_key = key
            best_len = len(key)
    if best_key:
        return models[best_key]
    # Fall back to configured fallback model
    fallback = pricing.get("fallback_model", "claude-sonnet-4-5")
    return models.get(fallback, {"input": 3.0, "output": 15.0,
                                  "cache_read": 0.30,
                                  "cache_write_5m": 3.75, "cache_write_1h": 6.0})


def compute_session_cost(usage: dict, rates: dict) -> float:
    """Compute USD cost for a session turn from token counts and pricing."""
    input_tok  = usage.get("input_tokens", 0)
    output_tok = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)

    cache_creation = usage.get("cache_creation", {})
    write_5m = cache_creation.get("ephemeral_5m_input_tokens", 0)
    write_1h = cache_creation.get("ephemeral_1h_input_tokens", 0)
    total_writes = usage.get("cache_creation_input_tokens", 0)
    write_standard = max(0, total_writes - write_5m - write_1h)

    cost = (
        input_tok * rates["input"] / 1_000_000
        + output_tok * rates["output"] / 1_000_000
        + cache_read * rates["cache_read"] / 1_000_000
        + write_5m * rates["cache_write_5m"] / 1_000_000
        + write_1h * rates["cache_write_1h"] / 1_000_000
        + write_standard * rates["cache_write_5m"] / 1_000_000  # standard write = 5m rate
    )
    return round(cost, 6)


def parse_session_stats(lines: list[dict], pricing: dict) -> dict:
    """Aggregate token counts, cost, and tool calls from a session's JSONL lines."""
    total_input = total_output = total_cache_read = total_cache_write = 0
    total_cost = 0.0
    tool_calls: dict[str, int] = {}
    model = ""

    for entry in lines:
        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage", {})
        if not usage:
            continue

        if not model:
            model = msg.get("model", "")
        rates = match_model_pricing(model, pricing)

        total_input       += usage.get("input_tokens", 0)
        total_output      += usage.get("output_tokens", 0)
        total_cache_read  += usage.get("cache_read_input_tokens", 0)
        total_cache_write += usage.get("cache_creation_input_tokens", 0)
        total_cost        += compute_session_cost(usage, rates)

        # Count tool calls from content array
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "unknown")
                    tool_calls[name] = tool_calls.get(name, 0) + 1

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_read_tokens": total_cache_read,
        "cache_write_tokens": total_cache_write,
        "cost_usd": round(total_cost, 6),
        "tool_calls": tool_calls,
    }


SESSION_PREFIX = "raw/sessions"

_DATE_PATH_RE = re.compile(
    rf"^{re.escape(SESSION_PREFIX)}/(\d{{4}})/(\d{{2}})/(\d{{2}})/"
)


def _date_from_key(key: str, fallback_mod: datetime) -> str:
    """Extract session date from R2 key path raw/sessions/YYYY/MM/DD/filename.

    Falls back to the object's LastModified date (must be timezone-aware) if
    the path doesn't match the expected structure.
    """
    m = _DATE_PATH_RE.match(key)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return date_of(fallback_mod)


def process_sessions(s3, bucket: str, watermark: str, pricing: dict) -> tuple[dict, str]:
    """Process session files with new files since watermark.

    For any date that has at least one file newer than the watermark, ALL files
    for that date are recomputed from scratch.  This prevents partial incremental
    batches from silently overwriting a day's previously accumulated stats.

    Returns:
        (ai_stats_by_date, new_watermark)
        ai_stats_by_date: {date_str: {sessions, input_tokens, ...}}
            Only dates that had at least one new file with parseable content
            are included; dates with only empty/malformed files are omitted so
            that any existing valid stats in ai_stats.json are preserved.
        new_watermark: ISO 8601 LastModified of most recently seen new file
    """
    all_objects = list_objects(s3, bucket, f"{SESSION_PREFIX}/")
    wm_dt = parse_ts(watermark)

    # Single pass: group objects by path-based date, find dirty dates, and
    # track the new watermark as a datetime to avoid repeated string parses.
    # Using the path date (raw/sessions/YYYY/MM/DD/…) rather than LastModified
    # ensures sessions are attributed to the day they ran, not the day they were
    # uploaded (late-night sessions can be uploaded after midnight).
    objects_by_date: dict[str, list] = {}
    dates_to_recompute: set[str] = set()
    new_wm_dt = wm_dt

    for obj in all_objects:
        last_mod = obj["LastModified"].replace(tzinfo=timezone.utc)
        date = _date_from_key(obj["Key"], last_mod)
        objects_by_date.setdefault(date, []).append(obj)
        if last_mod > wm_dt:
            dates_to_recompute.add(date)
            if last_mod > new_wm_dt:
                new_wm_dt = last_mod

    new_watermark = (
        new_wm_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if new_wm_dt > wm_dt else watermark
    )

    # Recompute complete stats for each affected date using ALL its files.
    # A date is only written to ai_stats if at least one file had parseable
    # content; fully-empty dates are skipped to protect existing valid stats.
    ai_stats: dict[str, dict] = {}
    for date in dates_to_recompute:
        day: dict = {
            "sessions": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "estimated_cost_usd": 0.0, "tool_calls": {},
        }
        for obj in objects_by_date.get(date, []):
            lines = get_jsonl_lines(s3, bucket, obj["Key"])
            if not lines:
                continue
            stats = parse_session_stats(lines, pricing)
            day["sessions"] += 1
            day["input_tokens"]       += stats["input_tokens"]
            day["output_tokens"]      += stats["output_tokens"]
            day["cache_read_tokens"]  += stats["cache_read_tokens"]
            day["cache_write_tokens"] += stats["cache_write_tokens"]
            day["estimated_cost_usd"]  = round(
                day["estimated_cost_usd"] + stats["cost_usd"], 6
            )
            for tool, count in stats["tool_calls"].items():
                day["tool_calls"][tool] = day["tool_calls"].get(tool, 0) + count
        if day["sessions"] > 0:
            ai_stats[date] = day

    return ai_stats, new_watermark

import pytest

from processor.sessions import (
    compute_session_cost,
    match_model_pricing,
    parse_session_stats,
)

PRICING = {
    "fallback_model": "claude-sonnet-4-5",
    "models": {
        "claude-opus-4-5": {"input": 5.0, "output": 25.0, "cache_read": 0.50,
                             "cache_write_5m": 6.25, "cache_write_1h": 10.0},
        "claude-opus-4":   {"input": 15.0, "output": 75.0, "cache_read": 1.50,
                             "cache_write_5m": 18.75, "cache_write_1h": 30.0},
        "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.30,
                               "cache_write_5m": 3.75, "cache_write_1h": 6.0},
    },
}


def test_match_model_pricing_exact():
    """claude-sonnet-4-5 matches the exact key."""
    rates = match_model_pricing("claude-sonnet-4-5", PRICING)
    assert rates["input"] == 3.0


def test_match_model_pricing_prefix_with_date_suffix():
    """claude-sonnet-4-5-20250929 matches claude-sonnet-4-5 via prefix."""
    rates = match_model_pricing("claude-sonnet-4-5-20250929", PRICING)
    assert rates["input"] == 3.0


def test_match_model_pricing_longer_key_wins():
    """claude-opus-4-5 (13 chars) beats claude-opus-4 (12 chars)."""
    rates = match_model_pricing("claude-opus-4-5-20250929", PRICING)
    assert rates["input"] == 5.0  # opus-4-5 price, not opus-4 price ($15)


def test_match_model_pricing_unknown_falls_back():
    """Unknown model returns fallback model rates."""
    rates = match_model_pricing("claude-unknown-model", PRICING)
    assert rates["input"] == 3.0  # fallback = claude-sonnet-4-5


def test_compute_session_cost_basic():
    """Cost = input + output + cache tokens at correct rates (per million)."""
    rates = {"input": 3.0, "output": 15.0, "cache_read": 0.30,
             "cache_write_5m": 3.75, "cache_write_1h": 6.0}
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_creation": {},
    }
    cost = compute_session_cost(usage, rates)
    assert cost == pytest.approx(3.0 + 15.0)  # $18.00


def test_parse_session_stats_counts_tool_calls():
    """Tool call counts are extracted from content blocks."""
    lines = [
        {
            "message": {
                "model": "claude-sonnet-4-5",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_creation": {},
                },
                "content": [
                    {"type": "tool_use", "name": "read_file"},
                    {"type": "tool_use", "name": "read_file"},
                    {"type": "tool_use", "name": "write_file"},
                    {"type": "text", "text": "Done"},
                ],
            }
        }
    ]
    stats = parse_session_stats(lines, PRICING)
    assert stats["tool_calls"]["read_file"] == 2
    assert stats["tool_calls"]["write_file"] == 1


def test_parse_session_stats_handles_missing_fields():
    """Lines without usage or model fields are skipped gracefully."""
    lines = [
        {"message": {}},              # no usage
        {"type": "human", "text": "hello"},  # no message key
        {
            "message": {
                "usage": {"input_tokens": 10, "output_tokens": 5,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0,
                           "cache_creation": {}},
                # no model field → falls back to fallback_model
            }
        },
    ]
    stats = parse_session_stats(lines, PRICING)
    assert stats["input_tokens"] == 10
    assert stats["output_tokens"] == 5

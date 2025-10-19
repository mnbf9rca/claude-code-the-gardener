# Tool descriptions

This document describes the current thinking for the tools needed for the plant care system.

## Thinking Service

### Write Tools

- `log_thought(observation, hypothesis, candidate_actions, reasoning, uncertainties, tags)` - Record reasoning and planning. Helps build a history of reasoning for review and learning.

Parameters:
- `observation` (string): What was observed about the plant
- `hypothesis` (string): Your hypothesis about what's happening
- `candidate_actions` (list): List of candidate actions with order, action type, and optional value
- `reasoning` (string): Your reasoning for this hypothesis
- `uncertainties` (string): What you're uncertain about
- `tags` (list): Tags for categorization (optional, default: [])

Returns:
```json
{
  "timestamp": "ISO8601",
  "success": true
}
```

### Query Tools

- `get_recent(n, offset)` - Returns last N thought entries with pagination
  - `n` (int): Number of recent thoughts (default 3, max 50)
  - `offset` (int): Number of entries to skip from the end for pagination (default 0)
  - Returns: `{"count": N, "thoughts": [...]}`

- `get_range(start_time, end_time)` - Entries within time window (ISO8601 format)
  - Returns: `{"count": N, "thoughts": [...]}`

- `search(keyword, hours)` - Search observations, hypotheses, and reasoning fields
  - `keyword` (string): Keyword to search for (case-insensitive)
  - `hours` (int): How many hours back to search (default 24)
  - Returns: `{"count": N, "thoughts": [...]}`

**State Management:**
- Keeps last 1000 thoughts in memory
- Full history persisted to disk in JSONL format
- Auto-loads on first tool invocation

## Action Log Service

### Write Tools

- `log_action(type, details)` - Record action with context. Creates a record of all actions for review and analysis.

Parameters:
- `type` (string): Type of action - must be one of: `water`, `light`, `observe`, `alert`
- `details` (object): Details about the action taken (flexible JSON)

Returns:
```json
{
  "timestamp": "ISO8601",
  "success": true
}
```

### Query Tools

- `get_recent(n, offset)` - Returns last N action entries with pagination
  - `n` (int): Number of recent actions (default 5, max 50)
  - `offset` (int): Number of entries to skip from the end for pagination (default 0)
  - Returns: `{"count": N, "actions": [...]}`

- `search(keyword, hours)` - Text search in action details
  - `keyword` (string): Keyword to search for (case-insensitive)
  - `hours` (int): How many hours back to search (default 24)
  - Returns: `{"count": N, "actions": [...]}`

**State Management:**
- Keeps last 1000 actions in memory
- Full history persisted to disk in JSONL format
- Auto-loads on first tool invocation

**Note:** For specialized queries like water usage or light timing, use the respective tool's query methods (e.g., `get_usage_24h()` on water_pump, `get_status()` on light).

## Plant Status Service

### Write Tools

- `write_status(status_object)` - **Must be called first each cycle.** Returns `{"proceed": true}` or `{"proceed": false, "reason": "text"}`.

```json
{
  "timestamp": "ISO8601",
  "sensor_reading": 1847,
  "water_24h": 150,
  "light_today": 240,
  "plant_state": "healthy|stressed|concerning|critical|unknown",
  "next_action_sequence": [
    {"order": 1, "action": "water", "value": 40},
    {"order": 2, "action": "light", "value": 60}
  ],
  "reasoning": "brief explanation"
}
```

## Moisture Sensor Service

### Query Tools

- `read()` - Returns `{"value": 1847, "timestamp": "ISO8601"}`

## Water Pump Service

### Write Tools

- `dispense(ml)` - Dispense water. Accepts integer 10-100. Returns `{"dispensed": 30, "remaining_24h": 470, "timestamp": "ISO8601"}`. Error if exceeds 500ml daily limit.

### Query Tools

- `get_usage_24h()` - Returns `{"used_ml": 150, "remaining_ml": 350, "events": 3}`

## Light Service

### Write Tools

- `turn_on(minutes)` - Activate grow light. Accepts integer 30-120. Returns `{"status": "on", "duration_minutes": 90, "off_at": "ISO8601"}`. Error if minimum 30min off-time not elapsed.

### Query Tools

- `get_status()` - Returns `{"status": "on|off", "last_on": "ISO8601", "last_off": "ISO8601", "can_activate": true, "minutes_until_available": 15}`

## Camera Service

### Write Tools

- `capture()` - Take photo. Returns `{"url": "http://192.168.1.x/photos/timestamp.jpg", "timestamp": "ISO8601"}`

## UTC Time Service

### Query Tools

- `get_current_time()` - Get current UTC time. Returns `{"timestamp": "ISO8601 UTC"}`

Use this tool to query the current date and time for temporal reasoning. All timestamps throughout the system use UTC to avoid timezone issues.

## Web Search Service

### Query Tools

- `search(query)` - Standard web search. Use for plant care research, symptom diagnosis, calibration data.
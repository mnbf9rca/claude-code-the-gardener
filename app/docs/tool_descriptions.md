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

- `save_notes(content, mode) - store a single unstructured note for later review, reuse, tracking across sessions. Although not disclosed to the agent, every time this is called a new file is created on disk with a timestamped filename for auditability and review.

Parameters:

- `content` (string): The note content (markdown supported). There is no size limit but extremely large notes may impact performance.
- `mode` (string): `replace` (default) to replace existing note, `append` to add to the existing note.

Returns:
```json
{
  "timestamp": "ISO8601",
  "note_length_chars": 1234
}
```

- `send_message_to_human(message, in_reply_to = None)` - Send a message to the human caretaker for review or action. This is for important alerts or requests for input.

Parameters:

- `message` (string): The message content. Include any relevant context, severity, and recommended actions. Accepts free text, markdown etc. up to 50,000 characters.
- `in_reply_to` (string): Optional message ID this is in reply to.

Returns:
```json
{
  "timestamp": "ISO8601",
  "message_id": "1234"
}
```

### Query Tools

- `get_recent_thoughts(n, offset)` - Returns last N thought entries with pagination
  - `n` (int): Number of recent thoughts (default 3, max 50)
  - `offset` (int): Number of entries to skip from the end for pagination (default 0)
  - Returns: `{"count": N, "thoughts": [...]}`

- `get_thoughts_in_range(start_time, end_time)` - Entries within time window (ISO8601 format)
  - Returns: `{"count": N, "thoughts": [...]}`

- `search_thoughts(keyword, hours)` - Search observations, hypotheses, and reasoning fields
  - `keyword` (string): Keyword to search for (case-insensitive)
  - `hours` (int): How many hours back to search (default 24)
  - Returns: `{"count": N, "thoughts": [...]}`

- `get_thought_history_bucketed(hours, samples_per_hour, aggregation, value_field, end_time)` - Get time-bucketed thought history for temporal analysis
  - `hours` (int): Time window in hours (how far back to query, default 24)
  - `samples_per_hour` (float): Bucket density - 6=every 10min, 1=hourly, 0.042=daily (default 6)
  - `aggregation` (string): Strategy: `first|last|middle` (sampling) or `count|sum|mean` (aggregation, default "middle")
  - `value_field` (string): Field to aggregate (required for sum/mean, optional)
  - `end_time` (string): End of time window in ISO8601 UTC (defaults to now, optional)
  - Returns: For sampling: List of thought dicts with full context. For aggregation: List of `{"bucket_start": str, "bucket_end": str, "value": number, "count": int}`

**State Management:**
- Keeps last 1000 thoughts in memory
- Full history persisted to disk in JSONL format
- Auto-loads on first tool invocation

- `fetch_notes()` - Retrieve the current note content (e.g. markdown, etc.). Returns an empty string if no note exists.

- `list_messages_from_human(limit=10, offset=0, include_content=True)` - Lists all messages sent from the human caretaker to the agent, sorted newest first. Returns an empty list if no messages exist.

Parameters:

- `limit` (int): Maximum number of messages to return (default 10, max 50)
- `offset` (int): Number of messages to skip for pagination (default 0)
- `include_content` (bool): If true, include the content of the messages in the response (default true)


Returns:

```json
{
  "messages": [
    {
      "message_id": "1234",
      "in_reply_to": "5678" or None,
      "timestamp": "ISO8601",
      "content": "string"
    }
  ]
}
```

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

- `get_recent_actions(n, offset)` - Returns last N action entries with pagination
  - `n` (int): Number of recent actions (default 5, max 50)
  - `offset` (int): Number of entries to skip from the end for pagination (default 0)
  - Returns: `{"count": N, "actions": [...]}`

- `search_actions(keyword, hours)` - Text search in action details
  - `keyword` (string): Keyword to search for (case-insensitive)
  - `hours` (int): How many hours back to search (default 24)
  - Returns: `{"count": N, "actions": [...]}`

- `get_action_history_bucketed(hours, samples_per_hour, aggregation, value_field, end_time)` - Get time-bucketed action log history for temporal analysis
  - `hours` (int): Time window in hours (how far back to query, default 24)
  - `samples_per_hour` (float): Bucket density - 6=every 10min, 1=hourly, 0.042=daily (default 6)
  - `aggregation` (string): Strategy: `first|last|middle` (sampling) or `count|sum|mean` (aggregation, default "middle")
  - `value_field` (string): Field to aggregate (required for sum/mean, optional)
  - `end_time` (string): End of time window in ISO8601 UTC (defaults to now, optional)
  - Returns: For sampling: List of action dicts with full context. For aggregation: List of `{"bucket_start": str, "bucket_end": str, "value": number, "count": int}`
  - Examples: Count of actions per day (last month): `hours=720, samples_per_hour=0.042, aggregation="count"`. Count of actions per hour (last week): `hours=168, samples_per_hour=1, aggregation="count"`

**State Management:**
- Keeps last 1000 actions in memory
- Full history persisted to disk in JSONL format
- Auto-loads on first tool invocation

**Note:** For specialized queries like water usage or light timing, use the respective tool's query methods (e.g., `get_water_usage_24h()` on water_pump, `get_light_status()` on light).

## Plant Status Service

### Write Tools

- `write_plant_status(status_object)` - **Must be called first each cycle.** Returns `{"proceed": true}` or `{"proceed": false, "reason": "text"}`.

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

- `read_moisture()` - Returns `{"value": 1847, "timestamp": "ISO8601"}`

- `get_moisture_history(hours, samples_per_hour, aggregation, value_field, end_time)` - Get time-bucketed moisture sensor history for temporal analysis
  - `hours` (int): Time window in hours (how far back to query, default 24)
  - `samples_per_hour` (float): Bucket density - 6=every 10min, 1=hourly, 0.042=daily (default 6)
  - `aggregation` (string): Strategy: `first|last|middle` (sampling) or `count|sum|mean` (aggregation, default "middle")
  - `value_field` (string): Field to aggregate (required for sum/mean, optional)
  - `end_time` (string): End of time window in ISO8601 UTC (defaults to now, optional)
  - Returns: For sampling: List of sensor reading dicts with full context. For aggregation: List of `{"bucket_start": str, "bucket_end": str, "value": number, "count": int}`

## Water Pump Service

### Write Tools

- `dispense_water(ml)` - Dispense water. Accepts integer 10-25. Returns `{"dispensed": 25, "remaining_24h": 475, "timestamp": "ISO8601"}`. Error if exceeds 500ml daily limit. NOTE: Maximum 25ml per event due to ESP32 30s safety limit. For larger amounts, trigger multiple sequential dispenses.

### Query Tools

- `get_water_usage_24h()` - Returns `{"used_ml": 150, "remaining_ml": 350, "events": 3}`

- `get_water_history(hours, samples_per_hour, aggregation, value_field, end_time)` - Get time-bucketed water dispensing history for temporal analysis
  - `hours` (int): Time window in hours (how far back to query, default 24)
  - `samples_per_hour` (float): Bucket density - 6=every 10min, 1=hourly, 0.042=daily (default 6)
  - `aggregation` (string): Strategy: `first|last|middle` (sampling) or `count|sum|mean` (aggregation, default "middle")
  - `value_field` (string): Field to aggregate (required for sum/mean, e.g., "ml_dispensed", optional)
  - `end_time` (string): End of time window in ISO8601 UTC (defaults to now, optional)
  - Returns: For sampling: List of water dispense event dicts with full context. For aggregation: List of `{"bucket_start": str, "bucket_end": str, "value": number, "count": int}`
  - Examples: Total ml dispensed per day (last 7 days): `hours=168, samples_per_hour=0.042, aggregation="sum", value_field="ml_dispensed"`

## Light Service

### Write Tools

- `turn_on_light(minutes)` - Activate grow light. Accepts integer 30-120. Returns `{"status": "on", "duration_minutes": 90, "off_at": "ISO8601"}`. Error if minimum 30min off-time not elapsed.

### Query Tools

- `get_light_status()` - Returns `{"status": "on|off", "last_on": "ISO8601", "last_off": "ISO8601", "can_activate": true, "minutes_until_available": 15}`

## Camera Service

### Write Tools

- `capture_photo()` - Take photo. Returns `{"url": "http://192.168.1.x/photos/timestamp.jpg", "timestamp": "ISO8601"}`

### Query Tools

- `get_camera_history_bucketed(hours, samples_per_hour, aggregation, value_field, end_time)` - Get time-bucketed camera usage history for temporal analysis
  - `hours` (int): Time window in hours (how far back to query, default 24)
  - `samples_per_hour` (float): Bucket density - 6=every 10min, 1=hourly, 0.042=daily (default 6)
  - `aggregation` (string): Strategy: `first|last|middle` (sampling) or `count|sum|mean` (aggregation, default "middle")
  - `value_field` (string): Field to aggregate (required for sum/mean, optional)
  - `end_time` (string): End of time window in ISO8601 UTC (defaults to now, optional)
  - Returns: For sampling: List of camera usage dicts with full context. For aggregation: List of `{"bucket_start": str, "bucket_end": str, "value": number, "count": int}`
  - Examples: Count of photos per day (last month): `hours=720, samples_per_hour=0.042, aggregation="count"`

## UTC Time Service

### Query Tools

- `get_current_time()` - Get current UTC time. Returns `{"timestamp": "ISO8601 UTC"}`

Use this tool to query the current date and time for temporal reasoning. All timestamps throughout the system use UTC to avoid timezone issues.

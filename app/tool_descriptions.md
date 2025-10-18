# Tool descriptions

This document describes the current thinking for the tools needed for the plant care system.

## Thinking Service

### Write Tools

- `log_thought(thought_object)` - Record reasoning and planning. Required before taking actions.

```json
{
  "timestamp": "ISO8601",
  "observation": "sensor dropped 200 points, leaves appear slightly wilted",
  "hypothesis": "soil drying faster due to increased light exposure",
  "candidate_actions": [
    {"order": 1, "action": "water", "value": 40},
    {"order": 2, "action": "observe", "value": null}
  ],
  "reasoning": "gradual increase to avoid overwatering",
  "uncertainties": "text",
  "tags": ["moisture", "observation"]
}
```

### Query Tools

- `get_recent(n)` - Returns last N thought entries (default n=3, max 20)
- `get_range(start_time, end_time)` - Entries within time window
- `search(keyword, hours=24)` - Search observations, hypotheses, and reasoning fields

## Action Log Service

### Write Tools

- `log_action(type, details)` - Record action with context. Types: `water|light|observe|alert`. Details is JSON with relevant fields.

### Query Tools

- `get_recent(n)` - Returns last N action entries (default n=5, max 50)
- `get_water_24h()` - Returns `{"total_ml": 150, "events": 3}`
- `get_light_today()` - Returns `{"total_minutes": 180, "activations": 2}`
- `get_sensor_history(hours)` - Array of `[timestamp, value]` pairs at 10-minute intervals
- `search(keyword, hours=24)` - Text search in observation fields, returns matching entries

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

## Web Search Service

### Query Tools

- `search(query)` - Standard web search. Use for plant care research, symptom diagnosis, calibration data.
# Dryer MQTT Topics (4 Rooms)

Base: `dryer/room{1..4}/...`

## Topics
- `dryer/room{1..4}/telemetry`  (periodic e.g. every 1s)  QoS1, retain=false
- `dryer/room{1..4}/state`      (event-driven: only when state changes) QoS1, retain=true
- `dryer/room{1..4}/cmd`        (commands) QoS1
- `dryer/room{1..4}/ack`        (command acknowledgements) QoS1

## Rules
- `telemetry` is for graphs (temp/hum/dryer_on/setpoint) — always periodic.
- `state` is for events (RUN/IDLE, dryer_on flips, cycle complete success, etc.)
- `state` is retained so subscribers immediately see last known state.

## Example telemetry
Topic: `dryer/room1/telemetry`
```json
{
    "ts":"2026-01-12T17:30:17+07:00",
    "temp_c":30.0,
    "hum_pct":61.6,
    "dryer_on":false,
    "setpoint_c":50.0
}
```

## Example state
Topic: dryer/room1/state
```json
{
  "ts":"2026-01-12T17:40:20+07:00",
  "cmd_id":"cmd-001",
  "mode":"IDLE",
  "dryer_on":false,
  "cycle":{"status":"COMPLETED","result":"success","reason":"duration_reached"}
}
```

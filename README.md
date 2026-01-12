# Rubber Dryer Dev Stack (local)

## Topics behavior
- telemetry: periodic (every 1s), retain=false
- state: event-driven (only on change), retain=true (latest snapshot)

## Run
1) `cp .env.example .env`
2) `make up`

## Check simulator
- `sudo apt install jq`
- `curl http://localhost:8000/healthz`
- `curl -s http://localhost:8000/api/rooms/1/telemetry | jq .`

## Subscribe MQTT (Watch)
install mosquitto-clients 
- `sudo apt install mosquitto-clients`

Telemetry:
- `mosquitto_sub -h localhost -p 1883 -t 'dryer/+/telemetry' -v`
- Or, for individual rooms only.:
  `mosquitto_sub -h localhost -p 1883 -t 'dryer/room1/telemetry' -v`

State:
- `mosquitto_sub -h localhost -p 1883 -t 'dryer/+/state' -v`

Cmd/Ack:
- `mosquitto_sub -h localhost -p 1883 -t 'dryer/+/ack' -v`

## Command send to PLC simulator.
```bash
curl -X PUT http://localhost:8000/api/rooms/1/profile \
  -H 'Content-Type: application/json' \
  -d '{"setpoint_c":60,"duration_s":1800}'

curl -X POST http://localhost:8000/api/rooms/1/cmd/start \
  -H 'Content-Type: application/json' \
  -d '{"cmd_id":"cmd-0001-start"}'
```

## Command send to Gateway.
```bash
mosquitto_pub -h localhost -p 1883 -t 'dryer/room1/cmd' -q 1 -m \
'{"ts":"'"$(date -Iseconds)"'","cmd_id":"cmd-001-start","type":"start","profile":{"setpoint_c":35,"duration_s":15}}'
```

## EMQX Dashboard
- http://localhost:18083
(EMQX mqtt on localhost:1884)

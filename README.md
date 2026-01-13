# Rubber Dryer System

## Architecture
Local services:
- Simulator -> Gateway -> Local Mosquitto (localhost-only on host)
- Mosquitto Bridge <-> EMQX Cloud Serverless (TLS 8883)
- Ingest subscribes local MQTT and writes into TimescaleDB

## Topics
Base: `dryer/room{1..4}/...`

- `telemetry` (periodic, e.g. every 1s, retain=false)
- `state` (event-driven: publish only when state changes, retain=true)
- `cmd` (cloud/backend publishes commands)
- `ack` (gateway responses)

## EMQX Cloud Serverless setup
1) Create **Serverless** deployment.
2) In Deployment → **Overview**
   - Copy Broker Address (e.g. `xxxxx...emqxsl.com`)
   - Download **CA certificate**
3) Access Control → Authentication: create users
   - `gateway_user` (for bridge/gateway)
   - `backend_user` (for MQTTX/backend)
4) Access Control → Authorization (Whitelist mode)
   - All Users: Deny `#` (Publish & Subscribe)
   - gateway_user:
     - Allow Publish: `dryer/+/telemetry`, `dryer/+/state`, `dryer/+/ack`, `dryer/+/alarm`
     - Allow Subscribe: `dryer/+/cmd`
   - backend_user:
     - Allow Subscribe: `dryer/#`
     - Allow Publish: `dryer/+/cmd` (if backend will send commands)

## MQTTX connection to EMQX Cloud (TLS 8883)
- Host: `<broker address>`
- Port: `8883`
- TLS: ON, set CA cert from Overview
- Username/Password: use `backend_user`

## Local Mosquitto
Host access is localhost-only:
- compose ports: `127.0.0.1:1883:1883`
- persistence enabled in `mosquitto.conf`

## Bridge config
File: `mosquitto/conf.d/bridge-emqxcloud.conf`
- OUT -> Cloud: `telemetry/state/ack/alarm`
- IN  <- Cloud: `cmd`

## Run
1) `cp .env.example .env`
2) `make up`

## Check simulator
- `sudo apt install jq`
- `curl http://localhost:8000/healthz`
- `curl -s http://localhost:8000/api/rooms/1/telemetry | jq .`

## Subscribe local MQTT (Watch)
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

## Command send to PLC simulator (unit test)
```bash
curl -X PUT http://localhost:8000/api/rooms/1/profile \
  -H 'Content-Type: application/json' \
  -d '{"setpoint_c":60,"duration_s":1800}'

curl -X POST http://localhost:8000/api/rooms/1/cmd/start \
  -H 'Content-Type: application/json' \
  -d '{"cmd_id":"cmd-0001-start"}'
```

## Command send to Gateway (unit test)
```bash
mosquitto_pub -h localhost -p 1883 -t 'dryer/room1/cmd' -q 1 -m \
'{"ts":"'"$(date -Iseconds)"'","cmd_id":"cmd-001-start","type":"start","profile":{"setpoint_c":35,"duration_s":15}}'
```

## MQTT Log
```bash
docker exec -it dryer-mosquitto sh -lc "tail -n 200 /mosquitto/log/mosquitto.log"
```

## Query TimescaleDB
```bash
sudo docker exec -it dryer-timescale psql -U dryer -d dryerdb -c \
"SELECT ts AT TIME ZONE 'Asia/Bangkok' AS ts_th, room, temp_c, hum_pct, dryer_on
 FROM telemetry ORDER BY ts DESC LIMIT 10;"
```

## Test Checklist (quick)
1) `sudo docker compose ps` -> all services Up

2) Local pub/sub:
  - `mosquitto_pub ... dryer/test`
  - `mosquitto_sub ... dryer/test`

3) Bridge connected:
  - check mosquitto log file

4) OUT local->cloud:
  - MQTTX subscribe `dryer/+/telemetry`, should see data

5) IN cloud->local->gateway:
  - MQTTX publish `dryer/room1/cmd`, local sees cmd + cloud sees ack

6) DB ingest:
  - query telemetry/state_events/acks show rows
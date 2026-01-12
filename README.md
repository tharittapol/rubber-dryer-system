# Rubber Dryer Dev Stack (local)

## Run
1) `cp .env.example .env`
2) `make up`

## Check simulator
- `sudo apt install jq`
- `curl http://localhost:8000/healthz`
- `curl -s http://localhost:8000/api/rooms/1/telemetry | jq .`

## Subscribe MQTT
install mosquitto-clients 
- `sudo apt install mosquitto-clients`
then:
- `mosquitto_sub -h localhost -p 1883 -t 'dryer/+/telemetry' -v`
- Or, for individual rooms only.:
  `mosquitto_sub -h localhost -p 1883 -t 'dryer/room1/telemetry' -v`

## EMQX Dashboard
- http://localhost:18083
(EMQX mqtt on localhost:1884)

## Command start/stop to view temperature and find a setpoint.
```bash
curl -X PUT http://localhost:8000/api/rooms/1/profile \
  -H 'Content-Type: application/json' \
  -d '{"setpoint_c":60,"duration_s":1800}'

curl -X POST http://localhost:8000/api/rooms/1/cmd/start \
  -H 'Content-Type: application/json' \
  -d '{"cmd_id":"cmd-0001-start"}'
```

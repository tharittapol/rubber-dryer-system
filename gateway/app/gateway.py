import os
import time
import json
import re
from datetime import datetime

import requests
import paho.mqtt.client as mqtt


MOSQ_HOST = os.getenv("MOSQUITTO_HOST", "mosquitto")
MOSQ_PORT = int(os.getenv("MOSQUITTO_PORT", "1883"))
SIM_BASE = os.getenv("SIMULATOR_BASE_URL", "http://simulator:8000")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SEC", "1"))

ROOMS = [1, 2, 3, 4]
CMD_TOPIC_RE = re.compile(r"^dryer/room(\d+)/cmd$")


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def http_get(path: str):
    r = requests.get(f"{SIM_BASE}{path}", timeout=3.0)
    r.raise_for_status()
    return r.json()


def http_put(path: str, payload: dict):
    r = requests.put(f"{SIM_BASE}{path}", json=payload, timeout=3.0)
    r.raise_for_status()
    return r.json()


def http_post(path: str, payload: dict):
    r = requests.post(f"{SIM_BASE}{path}", json=payload, timeout=3.0)
    r.raise_for_status()
    return r.json()


def publish_json(client: mqtt.Client, topic: str, payload: dict, qos: int = 1, retain: bool = False):
    client.publish(topic, json.dumps(payload), qos=qos, retain=retain)


def handle_cmd(room_id: int, cmd: dict, client: mqtt.Client):
    cmd_id = cmd.get("cmd_id")
    cmd_type = cmd.get("type")
    ack_topic = f"dryer/room{room_id}/ack"

    def ack(status: str, detail: str | None = None):
        payload = {"ts": now_iso(), "cmd_id": cmd_id or "", "status": status, "detail": detail}
        publish_json(client, ack_topic, payload, qos=1, retain=False)

    if not cmd_id or not cmd_type:
        ack("rejected", "missing cmd_id or type")
        return

    try:
        if cmd_type == "set_profile":
            profile = cmd.get("profile") or {}
            http_put(f"/api/rooms/{room_id}/profile", profile)
            ack("done", "profile updated")
            return

        if cmd_type == "start":
            profile = cmd.get("profile")
            if profile:
                http_put(f"/api/rooms/{room_id}/profile", profile)
            http_post(f"/api/rooms/{room_id}/cmd/start", {"cmd_id": cmd_id})
            ack("accepted", "start issued")
            return

        if cmd_type == "stop":
            http_post(f"/api/rooms/{room_id}/cmd/stop", {"cmd_id": cmd_id})
            ack("accepted", "stop issued")
            return

        ack("rejected", f"unknown type={cmd_type}")
    except Exception as e:
        ack("rejected", f"simulator error: {e}")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dryer-gateway")

    # per-room: last published state signature & last cycle meta
    last_sig = {rid: None for rid in ROOMS}
    last_cycle = {rid: None for rid in ROOMS}

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        print(f"[gateway] mqtt connected rc={reason_code}")
        _client.subscribe("dryer/+/cmd", qos=1)

    def on_message(_client, _userdata, msg):
        try:
            m = CMD_TOPIC_RE.match(msg.topic)
            if not m:
                return
            room_id = int(m.group(1))
            cmd = json.loads(msg.payload.decode("utf-8"))
            handle_cmd(room_id, cmd, _client)
        except Exception as e:
            print(f"[gateway] cmd parse/handle error topic={msg.topic} err={e}")

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MOSQ_HOST, MOSQ_PORT, keepalive=30)
    client.loop_start()

    print(f"[gateway] started mqtt={MOSQ_HOST}:{MOSQ_PORT}, sim={SIM_BASE}, interval={POLL_INTERVAL}s")

    while True:
        t0 = time.time()

        for room_id in ROOMS:
            try:
                telem = http_get(f"/api/rooms/{room_id}/telemetry")
                state = http_get(f"/api/rooms/{room_id}/state")
                evwrap = http_get(f"/api/rooms/{room_id}/events")
                events = evwrap.get("events") or []

                # 1) TELEMETRY (periodic)
                publish_json(
                    client,
                    f"dryer/room{room_id}/telemetry",
                    {
                        "ts": telem.get("ts", now_iso()),
                        "temp_c": telem["temp_c"],
                        "hum_pct": telem["hum_pct"],
                        "dryer_on": telem["dryer_on"],
                        "setpoint_c": telem["setpoint_c"],
                    },
                    qos=1,
                    retain=False,
                )

                # 2) STATE (event-driven + retained)
                # Update last_cycle meta if any event arrived
                force_publish = False

                for ev in events:
                    et = ev.get("type")
                    if et == "cycle_started":
                        last_cycle[room_id] = {"status": "RUNNING", "result": None, "reason": None}
                        force_publish = True
                    elif et == "cycle_complete":
                        last_cycle[room_id] = {
                            "status": "COMPLETED",
                            "result": ev.get("result", "success"),
                            "reason": ev.get("reason", "duration_reached"),
                        }
                        force_publish = True
                    elif et == "cycle_stopped":
                        last_cycle[room_id] = {"status": "STOPPED", "result": "done", "reason": "stopped_by_command"}
                        force_publish = True
                    elif et == "profile_updated":
                        # optional: treat as state change (so dashboard can react)
                        force_publish = True

                # compose state payload (snapshot)
                payload_state = {
                    "ts": state.get("ts", now_iso()),
                    "cmd_id": state.get("cmd_id", None),
                    "mode": state["mode"],
                    "dryer_on": state["dryer_on"],
                    "cycle": last_cycle[room_id],
                }

                # signature excludes ts (so we don't publish every poll)
                sig = (
                    payload_state["cmd_id"],
                    payload_state["mode"],
                    payload_state["dryer_on"],
                    None if payload_state["cycle"] is None else payload_state["cycle"].get("status"),
                    None if payload_state["cycle"] is None else payload_state["cycle"].get("result"),
                    None if payload_state["cycle"] is None else payload_state["cycle"].get("reason"),
                )

                if force_publish or sig != last_sig[room_id]:
                    publish_json(
                        client,
                        f"dryer/room{room_id}/state",
                        payload_state,
                        qos=1,
                        retain=True,
                    )
                    last_sig[room_id] = sig

            except Exception as e:
                print(f"[gateway] room{room_id} poll error: {e}")

        elapsed = time.time() - t0
        time.sleep(max(0.0, POLL_INTERVAL - elapsed))


if __name__ == "__main__":
    main()

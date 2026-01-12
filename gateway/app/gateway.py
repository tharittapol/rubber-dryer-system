import os
import time
import json
import requests
import paho.mqtt.client as mqtt
from datetime import datetime


MOSQ_HOST = os.getenv("MOSQUITTO_HOST", "mosquitto")
MOSQ_PORT = int(os.getenv("MOSQUITTO_PORT", "1883"))
SIM_BASE = os.getenv("SIMULATOR_BASE_URL", "http://simulator:8000")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL_SEC", "1"))

ROOMS = [1, 2, 3, 4]


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def poll_room(room_id: int) -> dict:
    url = f"{SIM_BASE}/api/rooms/{room_id}/telemetry"
    r = requests.get(url, timeout=2.0)
    r.raise_for_status()
    return r.json()


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dryer-gateway")
    client.connect(MOSQ_HOST, MOSQ_PORT, keepalive=30)
    client.loop_start()

    print(f"[gateway] connected mqtt={MOSQ_HOST}:{MOSQ_PORT}, sim={SIM_BASE}, interval={POLL_INTERVAL}s")

    while True:
        t0 = time.time()
        for room_id in ROOMS:
            try:
                telem = poll_room(room_id)

                topic = f"dryer/room{room_id}/telemetry"
                payload = {
                    "ts": telem.get("ts", now_iso()),
                    "cmd_id": telem.get("cmd_id", None),
                    "temp_c": telem["temp_c"],
                    "hum_pct": telem["hum_pct"],
                    "running": telem["running"],
                    "setpoint_c": telem["setpoint_c"],
                }

                client.publish(topic, json.dumps(payload), qos=0, retain=False)
            except Exception as e:
                print(f"[gateway] room{room_id} error: {e}")

        # ให้รอบใกล้ 1s
        elapsed = time.time() - t0
        sleep_s = max(0.0, POLL_INTERVAL - elapsed)
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()

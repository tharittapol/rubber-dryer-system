import os, json, re
from datetime import datetime
import psycopg2
import paho.mqtt.client as mqtt

MOSQ_HOST = os.getenv("MOSQUITTO_HOST", "mosquitto")
MOSQ_PORT = int(os.getenv("MOSQUITTO_PORT", "1883"))

PGHOST = os.getenv("PGHOST", "timescaledb")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("POSTGRES_USER", "dryer")
PGPASS = os.getenv("POSTGRES_PASSWORD", "dryerpass")
PGDB   = os.getenv("POSTGRES_DB", "dryerdb")

TOPIC_RE = re.compile(r"^dryer/room(\d+)/(telemetry|state|alarm|ack)$")

def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)

def get_conn():
    return psycopg2.connect(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASS, dbname=PGDB)

def on_connect(client, userdata, flags, reason_code, properties):
    print("[ingest] connected, subscribing...")
    client.subscribe("dryer/+/telemetry", qos=1)
    client.subscribe("dryer/+/state", qos=1)
    client.subscribe("dryer/+/ack", qos=1)
    client.subscribe("dryer/+/alarm", qos=1)

def on_message(client, userdata, msg):
    m = TOPIC_RE.match(msg.topic)
    if not m:
        return

    room = int(m.group(1))
    kind = m.group(2)

    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        ts = parse_ts(payload["ts"])
        raw = json.dumps(payload)
    except Exception as e:
        print(f"[ingest] bad json topic={msg.topic} err={e}")
        return

    pg = userdata["pg"]
    try:
        with pg.cursor() as cur:
            if kind == "telemetry":
                cur.execute(
                    """
                    INSERT INTO telemetry (ts, room, temp_c, hum_pct, dryer_on, setpoint_c, raw)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (ts, room, payload.get("temp_c"), payload.get("hum_pct"),
                     payload.get("dryer_on"), payload.get("setpoint_c"), raw)
                )

            elif kind == "state":
                cycle = payload.get("cycle") or {}
                cur.execute(
                    """
                    INSERT INTO state_events
                      (ts, room, cmd_id, mode, dryer_on, cycle_status, cycle_result, cycle_reason, raw)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (ts, room, payload.get("cmd_id"), payload.get("mode"), payload.get("dryer_on"),
                     cycle.get("status"), cycle.get("result"), cycle.get("reason"), raw)
                )

            elif kind == "ack":
                cur.execute(
                    """
                    INSERT INTO acks (ts, room, cmd_id, status, detail, raw)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (ts, room, payload.get("cmd_id"), payload.get("status"), payload.get("detail"), raw)
                )

            elif kind == "alarm":
                cur.execute(
                    """
                    INSERT INTO alarms (ts, room, cmd_id, code, level, message, raw)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (ts, room, payload.get("cmd_id"), payload.get("code"),
                     payload.get("level"), payload.get("message"), raw)
                )

        pg.commit()
    except Exception as e:
        pg.rollback()
        print(f"[ingest] db error topic={msg.topic} err={e}")

def main():
    pg = get_conn()
    userdata = {"pg": pg}

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dryer-ingest")
    client.user_data_set(userdata)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MOSQ_HOST, MOSQ_PORT, keepalive=30)
    client.loop_forever()

if __name__ == "__main__":
    main()

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- telemetry (periodic)
CREATE TABLE IF NOT EXISTS telemetry (
  ts          timestamptz NOT NULL,
  room        int         NOT NULL,
  temp_c      double precision,
  hum_pct     double precision,
  dryer_on    boolean,
  setpoint_c  double precision,
  raw         jsonb
);
SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE);

-- state (event-driven)
CREATE TABLE IF NOT EXISTS state_events (
  ts       timestamptz NOT NULL,
  room     int         NOT NULL,
  cmd_id   text,
  mode     text,
  dryer_on boolean,
  cycle_status text,
  cycle_result text,
  cycle_reason text,
  raw      jsonb
);
SELECT create_hypertable('state_events', 'ts', if_not_exists => TRUE);

-- ack (event-driven)
CREATE TABLE IF NOT EXISTS acks (
  ts      timestamptz NOT NULL,
  room    int         NOT NULL,
  cmd_id  text,
  status  text,
  detail  text,
  raw     jsonb
);
SELECT create_hypertable('acks', 'ts', if_not_exists => TRUE);

-- alarm (event-driven)
CREATE TABLE IF NOT EXISTS alarms (
  ts      timestamptz NOT NULL,
  room    int         NOT NULL,
  cmd_id  text,
  code    text,
  level   text,
  message text,
  raw     jsonb
);
SELECT create_hypertable('alarms', 'ts', if_not_exists => TRUE);

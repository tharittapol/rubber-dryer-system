CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS telemetry (
  ts          timestamptz NOT NULL,
  room        int         NOT NULL,
  temp_c      double precision NOT NULL,
  hum_pct     double precision NOT NULL,
  running     boolean NOT NULL,
  setpoint_c  double precision NOT NULL,
  cmd_id      text
);

SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE);

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def now_dt() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_dt().isoformat(timespec="seconds")


@dataclass
class RoomMemory:
    # Process values
    temp_c: float = 30.0
    hum_pct: float = 60.0

    # Profile
    setpoint_c: float = 50.0
    duration_s: int = 1800

    # Control / cycle
    cycle_active: bool = False
    dryer_on: bool = False
    cycle_cmd_id: Optional[str] = None
    cycle_start: Optional[datetime] = None
    cycle_end: Optional[datetime] = None

    # last cycle meta (for state snapshot)
    last_cycle: Optional[dict] = None

    # Anti-chatter
    hysteresis_c: float = 2.0
    min_on_s: int = 15
    min_off_s: int = 15
    last_switch: datetime = field(default_factory=now_dt)

    # One-shot events (gateway will pop)
    events: List[dict] = field(default_factory=list)


class ProfileIn(BaseModel):
    setpoint_c: float = Field(..., ge=0, le=120)
    duration_s: int = Field(..., ge=1, le=24 * 3600)


class CmdIn(BaseModel):
    cmd_id: str = Field(..., min_length=8)


app = FastAPI(title="PLC Simulator", version="0.3.0")

ROOMS: Dict[int, RoomMemory] = {i: RoomMemory() for i in range(1, 5)}


@app.get("/healthz")
def healthz():
    return {"ok": True}


def get_room(room_id: int) -> RoomMemory:
    room = ROOMS.get(room_id)
    if not room:
        raise HTTPException(404, "room not found")
    return room


@app.get("/api/rooms/{room_id}/telemetry")
def get_telemetry(room_id: int):
    room = get_room(room_id)
    return {
        "ts": now_iso(),
        "temp_c": round(room.temp_c, 2),
        "hum_pct": round(room.hum_pct, 2),
        "dryer_on": room.dryer_on,
        "setpoint_c": room.setpoint_c,
    }


@app.get("/api/rooms/{room_id}/state")
def get_state(room_id: int):
    room = get_room(room_id)
    mode = "RUN" if room.cycle_active else "IDLE"
    return {
        "ts": now_iso(),
        "cmd_id": room.cycle_cmd_id,
        "mode": mode,
        "dryer_on": room.dryer_on,
        "cycle": room.last_cycle
    }


@app.get("/api/rooms/{room_id}/events")
def pop_events(room_id: int):
    room = get_room(room_id)
    ev = room.events[:]
    room.events.clear()
    return {"ts": now_iso(), "events": ev}


@app.put("/api/rooms/{room_id}/profile")
def set_profile(room_id: int, body: ProfileIn):
    room = get_room(room_id)
    room.setpoint_c = float(body.setpoint_c)
    room.duration_s = int(body.duration_s)

    room.events.append({
        "ts": now_iso(),
        "type": "profile_updated",
        "setpoint_c": room.setpoint_c,
        "duration_s": room.duration_s
    })
    return {"ok": True, "ts": now_iso(), "room": room_id}


@app.post("/api/rooms/{room_id}/cmd/start")
def cmd_start(room_id: int, body: CmdIn):
    room = get_room(room_id)

    room.cycle_active = True
    room.dryer_on = True
    room.cycle_cmd_id = body.cmd_id
    room.cycle_start = now_dt()
    room.cycle_end = room.cycle_start + timedelta(seconds=room.duration_s)
    room.last_switch = now_dt()

    room.last_cycle = {"status": "RUNNING", "result": None, "reason": None}

    room.events.append({
        "ts": now_iso(),
        "type": "cycle_started",
        "cmd_id": body.cmd_id
    })
    return {"ok": True, "ts": now_iso(), "room": room_id, "cmd_id": body.cmd_id}


@app.post("/api/rooms/{room_id}/cmd/stop")
def cmd_stop(room_id: int, body: CmdIn):
    room = get_room(room_id)

    room.cycle_active = False
    room.dryer_on = False
    room.cycle_cmd_id = None
    room.cycle_start = None
    room.cycle_end = None
    room.last_switch = now_dt()

    room.last_cycle = {"status": "STOPPED", "result": "done", "reason": "stopped_by_command"}

    room.events.append({
        "ts": now_iso(),
        "type": "cycle_stopped",
        "cmd_id": body.cmd_id
    })
    return {"ok": True, "ts": now_iso(), "room": room_id, "cmd_id": body.cmd_id}


async def process_loop():
    ambient = 30.0
    tau_heat = 40.0
    tau_cool = 80.0

    while True:
        dt = 1.0
        now = now_dt()

        for room in ROOMS.values():
            # duration complete
            if room.cycle_active and room.cycle_end and now >= room.cycle_end:
                done_cmd = room.cycle_cmd_id

                room.cycle_active = False
                room.dryer_on = False
                room.cycle_cmd_id = None
                room.cycle_start = None
                room.cycle_end = None
                room.last_switch = now

                room.last_cycle = {"status": "COMPLETED", "result": "success", "reason": "duration_reached"}

                room.events.append({
                    "ts": now_iso(),
                    "type": "cycle_complete",
                    "cmd_id": done_cmd,
                    "result": "success",
                    "reason": "duration_reached"
                })

            # dryer control (anti-chatter + hysteresis)
            if room.cycle_active:
                since = (now - room.last_switch).total_seconds()

                # OFF at/above setpoint (respect min_on)
                if room.dryer_on and room.temp_c >= room.setpoint_c and since >= room.min_on_s:
                    room.dryer_on = False
                    room.last_switch = now

                # ON when below setpoint - hysteresis (respect min_off)
                if (not room.dryer_on) and room.temp_c <= (room.setpoint_c - room.hysteresis_c) and since >= room.min_off_s:
                    room.dryer_on = True
                    room.last_switch = now

            # process model
            target = room.setpoint_c if room.dryer_on else ambient
            tau = tau_heat if room.dryer_on else tau_cool
            room.temp_c += (target - room.temp_c) / tau * dt

            # humidity (simple)
            room.hum_pct += (-0.08 * (room.temp_c - ambient)) * 0.02
            room.hum_pct += 0.01 # small drift up
            room.hum_pct = max(0.0, min(100.0, room.hum_pct))

        await asyncio.sleep(1.0)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(process_loop())

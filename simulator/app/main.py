from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def now_iso() -> str:
    # can also use local timezone in container (TZ=Asia/Bangkok)
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class RoomMemory:
    # Memory map (concept)
    # D1000.. telemetry
    # D1100.. profile
    # M1200.. cmd/state bits
    D: Dict[int, float] = field(default_factory=dict)
    M: Dict[int, int] = field(default_factory=dict)

    # Simple variables
    temp_c: float = 30.0
    hum_pct: float = 60.0
    setpoint_c: float = 50.0
    duration_s: int = 1800
    running: bool = False
    last_cmd_id: Optional[str] = None


class ProfileIn(BaseModel):
    setpoint_c: float = Field(..., ge=0, le=120)
    duration_s: int = Field(..., ge=1, le=24 * 3600)


class CmdIn(BaseModel):
    cmd_id: str = Field(..., min_length=8)


app = FastAPI(title="PLC Simulator", version="0.1.0")

ROOMS: Dict[int, RoomMemory] = {i: RoomMemory() for i in range(1, 5)}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/rooms/{room_id}/telemetry")
def get_telemetry(room_id: int):
    room = ROOMS.get(room_id)
    if not room:
        raise HTTPException(404, "room not found")

    # D1000 update... (showing mapping concept)
    room.D[1000] = room.temp_c
    room.D[1001] = room.hum_pct
    room.D[1002] = 1.0 if room.running else 0.0
    room.D[1100] = room.setpoint_c
    room.D[1101] = float(room.duration_s)

    return {
        "ts": now_iso(),
        "cmd_id": room.last_cmd_id,
        "temp_c": round(room.temp_c, 2),
        "hum_pct": round(room.hum_pct, 2),
        "running": room.running,
        "setpoint_c": room.setpoint_c,
    }


@app.put("/api/rooms/{room_id}/profile")
def set_profile(room_id: int, body: ProfileIn):
    room = ROOMS.get(room_id)
    if not room:
        raise HTTPException(404, "room not found")

    room.setpoint_c = float(body.setpoint_c)
    room.duration_s = int(body.duration_s)

    # D1100.. profile
    room.D[1100] = room.setpoint_c
    room.D[1101] = float(room.duration_s)
    return {"ok": True, "ts": now_iso(), "room": room_id}


@app.post("/api/rooms/{room_id}/cmd/start")
def cmd_start(room_id: int, body: CmdIn):
    room = ROOMS.get(room_id)
    if not room:
        raise HTTPException(404, "room not found")

    room.running = True
    room.last_cmd_id = body.cmd_id

    # M1200.. bits
    room.M[1200] = 1  # RUN bit
    return {"ok": True, "ts": now_iso(), "room": room_id, "cmd_id": body.cmd_id}


@app.post("/api/rooms/{room_id}/cmd/stop")
def cmd_stop(room_id: int, body: CmdIn):
    room = ROOMS.get(room_id)
    if not room:
        raise HTTPException(404, "room not found")

    room.running = False
    room.last_cmd_id = body.cmd_id
    room.M[1200] = 0
    return {"ok": True, "ts": now_iso(), "room": room_id, "cmd_id": body.cmd_id}


@app.get("/api/rooms/{room_id}/memory")
def get_memory(room_id: int):
    room = ROOMS.get(room_id)
    if not room:
        raise HTTPException(404, "room not found")
    return {"ts": now_iso(), "D": room.D, "M": room.M}


async def process_loop():
    """
    Simple process model:
    - temp: first-order goes to the setpoint if running.
      if not running → return to ambient
    - hum: changes with temp roughly + small drift
    """
    ambient = 30.0
    tau_run = 40.0     # The less, the faster
    tau_idle = 80.0

    while True:
        dt = 1.0
        for room in ROOMS.values():
            target = room.setpoint_c if room.running else ambient
            tau = tau_run if room.running else tau_idle

            # first-order: x += (target - x)/tau * dt
            room.temp_c += (target - room.temp_c) / tau * dt

            # Simple humidity: higher temperature -> lower humidity (assuming). 
            # + small drift
            room.hum_pct += (-0.08 * (room.temp_c - ambient)) * 0.02
            room.hum_pct += 0.05  # drift
            # clamp
            room.hum_pct = max(0.0, min(100.0, room.hum_pct))

        await asyncio.sleep(1.0)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(process_loop())

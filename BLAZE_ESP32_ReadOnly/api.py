"""Read-only ESP32 telemetry receiver for supervised low-voltage bench tests."""
from __future__ import annotations

import os
import secrets
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from database import init_db, add_reading

app = FastAPI(
    title="BLAZE Read-only Telemetry API",
    description="Receives temperature telemetry only. No actuator endpoints exist.",
    version="1.0.0",
)

init_db()


class TelemetryIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=40)
    temperature: float | None = Field(default=None, ge=-20, le=1024)
    sensor_status: Literal["NORMAL", "FAULT"]


@app.get("/")
def root():
    return {
        "service": "BLAZE read-only telemetry",
        "status": "online",
        "actuator_control": False,
    }


@app.post("/telemetry")
def receive_telemetry(
    payload: TelemetryIn,
    x_device_token: str | None = Header(default=None),
):
    expected = os.getenv("BLAZE_DEVICE_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Server token is not configured. Set BLAZE_DEVICE_TOKEN.",
        )
    if not x_device_token or not secrets.compare_digest(x_device_token, expected):
        raise HTTPException(status_code=401, detail="Invalid device token.")

    if payload.sensor_status == "NORMAL" and payload.temperature is None:
        raise HTTPException(
            status_code=422,
            detail="A NORMAL reading must include a numeric temperature.",
        )
    if payload.sensor_status == "FAULT" and payload.temperature is not None:
        # Do not store a stale/invalid number as a valid temperature.
        temperature = None
        state = "SENSOR_FAULT"
    else:
        temperature = payload.temperature
        state = "MONITORING" if payload.sensor_status == "NORMAL" else "SENSOR_FAULT"

    add_reading(
        temperature=temperature,
        sensor_status=payload.sensor_status,
        state=state,
        source=f"ESP32:{payload.device_id}",
    )
    return {"accepted": True, "device_id": payload.device_id, "state": state}

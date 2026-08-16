"""Live valve controller that drives the watering engine on a tick schedule.

The engine (`smart_watering_system.engine.decide`) is designed to be called
once per morning, not repeatedly while a valve is open.  This controller
honors that contract:

  * It calls `decide()` only when the valve is **closed**.
  * When `decide()` returns a non-zero duration, it opens the valve, waits
    for exactly that long, then closes it and records the event.
  * While the valve is open, it does *not* call `decide()` again — no
    overlapping commands, no premature closes from a 0-decision.
  * After closing, it resumes calling `decide()`.  At demand >= 85 the
    engine's cadence floor is 0 days, so it can open the valve again the
    same morning (subject to the budget and moisture gates).

Persistence contract
--------------------
Every valve transition is recorded as a `WaterTickEvent` row:
  * `valve_open=True`  — at the moment the valve opens.
  * `valve_open=False` — at the moment the valve closes.

The open duration is therefore the gap between two consecutive rows.
`watering_state_service.get_watering_state` reconstructs `last_watering`
and `seconds_open_last_3_days` from this log, so a restart loses nothing.

Because the controller is `async` and the wait is `asyncio.sleep`, a
restart while the valve is open would leave a dangling `valve_open=True`
row.  On startup the controller detects this and closes it, recording the
close at the restart time (the actual open duration is unknown — it's
measured to the restart, which is the best available estimate).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy.orm import Session

from database.models import WaterTickEvent, engine as db_engine
from service.watering_state_service import get_watering_state
from smart_watering_system.engine import decide

log = logging.getLogger(__name__)

# How often to poll `decide()` when the valve is closed.  The engine only
# waters in the 04:00-10:00 window, so most ticks are no-ops; an hourly
# tick is fine for resolution and cheap on the Open-Meteo client (which is
# called at most once per tick).
TICK_INTERVAL_SEC = 60 * 60  # 1 hour


class ValveController:
    """Guards the engine from being called while the valve is open.

    `valve_opener` is the hardware abstraction: an async callable that
    opens the physical valve for `seconds` and returns when it should
    close (or is given a cancel).  In production this wraps GPIO; in
    tests it can be a no-op that just sleeps.
    """

    def __init__(
        self,
        valve_opener: Callable[[float], Awaitable[None]],
        tick_interval_sec: int = TICK_INTERVAL_SEC,
    ):
        self._valve_opener = valve_opener
        self._tick_interval = tick_interval_sec
        self._valve_open = False
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        """Main loop: tick forever, calling `decide()` when the valve is closed."""
        await self._recover_open_valve()
        while True:
            try:
                await self._tick()
            except Exception:
                log.exception("tick failed")
            await asyncio.sleep(self._tick_interval)

    async def _tick(self) -> None:
        if self._valve_open:
            # Engine contract: don't re-evaluate while the valve is open.
            return

        now = datetime.now()
        with Session(db_engine) as db:
            last_watering, seconds_last_3d = get_watering_state(db, now=now)
            weather = await self._fetch_weather(db)
            demand = await self._get_demand(db)
            decision = decide(
                now=now,
                hourly_times=weather.hourly.time,
                precipitation=weather.hourly.precipitation,
                soil_temperature_0cm=weather.hourly.soil_temperature_0cm,
                soil_moisture_1_to_3cm=weather.hourly.soil_moisture_1_to_3cm,
                snow_depth=weather.hourly.snow_depth,
                watering_demand=demand,
                last_watering=last_watering,
                seconds_open_last_3_days=seconds_last_3d,
                et0_fao_evapotranspiration=weather.hourly.et0_fao_evapotranspiration,
            )

        if decision.seconds > 0:
            await self._open_valve(now, decision.seconds)

    async def _open_valve(self, opened_at: datetime, seconds: float) -> None:
        """Record the open, drive the hardware, then record the close."""
        self._valve_open = True
        self._write_event(True)
        try:
            await self._valve_opener(seconds)
        finally:
            # Always close — even if the opener was cancelled or raised.
            self._write_event(False)
            self._valve_open = False

    def _write_event(self, valve_open: bool) -> None:
        with Session(db_engine) as db:
            db.add(WaterTickEvent(valve_open=valve_open))
            db.commit()

    async def _recover_open_valve(self) -> None:
        """On startup, if the last persisted event is `valve_open=True`,
        close it so the duration log isn't corrupted."""
        with Session(db_engine) as db:
            last = (
                db.query(WaterTickEvent)
                .order_by(WaterTickEvent.created_at.desc())
                .first()
            )
            if last is not None and last.valve_open:
                log.warning("found dangling open valve event at %s; closing", last.created_at)
                db.add(WaterTickEvent(valve_open=False))
                db.commit()

    # ── overridable hooks ───────────────────────────────────────────────
    async def _fetch_weather(self, db: Session):
        """Fetch the forecast for the selected profile's city."""
        from clients.geocoding_open_meteo import geocoding_open_meteo_api
        from clients.open_meteo import open_meteo_api
        from service.shared.selected_profile_service import get_selected_profile

        profile = await get_selected_profile(db)
        geocodes = await geocoding_open_meteo_api.search(profile.city)
        geocode = geocodes.results[0]
        return await open_meteo_api.get_forecast(geocode.latitude, geocode.longitude)

    async def _get_demand(self, db: Session) -> float:
        from service.shared.selected_profile_service import get_selected_profile

        profile = await get_selected_profile(db)
        return profile.watering_demand

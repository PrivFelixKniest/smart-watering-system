"""Live valve controller that drives the watering engine on a tick schedule.

The controller is the single owner of the physical valve state and the
watering-event log.  Both the automated engine and the manual user
controls go through the same two methods:

  * ``open_valve()``  — idempotent open (no-op if already open).
  * ``close_valve()`` — idempotent close (no-op if already closed).

Because both callers funnel through these methods, the engine and the
user are symmetric: each acts as "another user trying to turn the water
on and off".  If the valve is already in the requested state, nothing
happens.  If the engine opened it and the user closes it, it closes as
normal (the engine's open-cycle sleep is cancelled).  Every transition
is recorded as a ``WaterTickEvent`` row, so the event log is the source
of truth and survives restarts.

Engine contract
---------------
The engine (``smart_watering_system.engine.decide``) is designed to be
called once per morning, not repeatedly while a valve is open.  This
controller honors that contract:

  * It calls ``decide()`` only when the valve is **closed**.
  * When ``decide()`` returns a non-zero duration, it opens the valve,
    waits for exactly that long, then closes it and records the event.
  * While the valve is open, it does *not* call ``decide()`` again — no
    overlapping commands, no premature closes from a 0-decision.
  * After closing, it resumes calling ``decide()``.

Persistence contract
--------------------
Every valve transition is recorded as a ``WaterTickEvent`` row:
  * `valve_open=True`  — at the moment the valve opens.
  * `valve_open=False` — at the moment the valve closes.

The open duration is therefore the gap between two consecutive rows.
`watering_state_service.get_watering_state` reconstructs `last_watering`
and `seconds_open_last_3_days` from this log, so a restart loses nothing.

Manual override
---------------
A manual ``open_valve()`` while the valve is closed opens it indefinitely
(it stays open until something — the user, the engine, or a restart —
closes it).  A manual ``close_valve()`` while the engine is in its
open-cycle sleep cancels that sleep and closes immediately.  The engine's
next tick then re-evaluates from scratch.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import WaterTickEvent, engine as db_engine
from service.watering_state_service import get_watering_state
from smart_watering_system.engine import decide
from smart_watering_system.gpio import ValveHardware, make_valve_hardware

log = logging.getLogger(__name__)

# How often to poll `decide()` when the valve is closed.  The engine only
# waters in the 04:00-10:00 window, so most ticks are no-ops; an hourly
# tick is fine for resolution and cheap on the Open-Meteo client (which is
# called at most once per tick).
TICK_INTERVAL_SEC = 60 * 60  # 1 hour


class ValveController:
    """Single owner of the valve state and the watering-event log.

    Both the engine loop and the manual user controls call
    ``open_valve()`` / ``close_valve()``.  These are idempotent and
    lock-protected, so concurrent calls from the engine task and the API
    request handlers serialize cleanly and never double-write events.
    """

    def __init__(
        self,
        hardware: ValveHardware,
        tick_interval_sec: int = TICK_INTERVAL_SEC,
    ):
        self._hardware = hardware
        self._tick_interval = tick_interval_sec
        self._valve_open = False
        # Serializes state mutation + event writes between the engine
        # task and manual API calls.
        self._lock = asyncio.Lock()
        # The engine's current open-cycle task (open → sleep → close).
        # Tracked so a manual close can cancel the sleep and close
        # immediately instead of waiting for the timer to expire.
        self._engine_open_task: Optional[asyncio.Task] = None

    # ── public API (manual + engine) ───────────────────────────────
    async def open_valve(self) -> bool:
        """Open the valve. Idempotent. Returns True iff state changed."""
        async with self._lock:
            if self._valve_open:
                return False
            await self._hardware.on()
            self._valve_open = True
            self._write_event(True)
            log.info("valve OPEN")
            return True

    async def close_valve(self) -> bool:
        """Close the valve. Idempotent. Cancels any engine open-cycle.
        Returns True iff state changed."""
        async with self._lock:
            if not self._valve_open:
                return False
            # If the engine is sleeping inside its open cycle, cancel
            # that sleep so we don't keep the valve open until the
            # timer expires.  The cancelled cycle returns without
            # re-closing (we close here, holding the lock).
            if self._engine_open_task is not None and not self._engine_open_task.done():
                self._engine_open_task.cancel()
                self._engine_open_task = None
            await self._hardware.off()
            self._valve_open = False
            self._write_event(False)
            log.info("valve CLOSED")
            return True

    @property
    def is_open(self) -> bool:
        return self._valve_open

    # ── engine loop ────────────────────────────────────────────────
    async def run(self) -> None:
        """Main loop: tick forever, calling `decide()` when the valve is closed."""
        await self._recover_open_valve()
        try:
            while True:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("tick failed")
                await asyncio.sleep(self._tick_interval)
        finally:
            # On shutdown (loop task cancelled), tear down any in-flight
            # open cycle so it doesn't leak, and force the hardware off
            # so a Pi doesn't keep the valve physically open.  The event
            # log is left to _recover_open_valve on the next startup.
            if self._engine_open_task is not None and not self._engine_open_task.done():
                self._engine_open_task.cancel()
            try:
                await self._hardware.off()
            except Exception:
                log.exception("failed to force valve off on shutdown")

    async def _tick(self) -> None:
        if self._valve_open:
            # Engine contract: don't re-evaluate while the valve is open
            # (whether the engine or the user opened it).
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
            # Run the open-cycle as its own task so a manual close can
            # cancel just the sleep (via close_valve) without killing
            # this loop.  We await it so the next tick doesn't overlap.
            #
            # NOTE: we deliberately do *not* clear ``_engine_open_task``
            # here after the await — run()'s finally needs the
            # reference to cancel a still-running cycle on shutdown,
            # and close_valve clears it when it cancels a manual close.
            self._engine_open_task = asyncio.create_task(
                self._engine_open_cycle(decision.seconds)
            )
            try:
                await self._engine_open_task
            except asyncio.CancelledError:
                # Shutdown cancelled the loop while waiting on the
                # cycle.  Re-raise so run()'s finally cleans up.
                raise

    async def _engine_open_cycle(self, seconds: float) -> None:
        """Open the valve, wait `seconds`, then close it.

        If cancelled (by a manual close or shutdown), the closer has
        already recorded the close event, so we just stop — no
        double-close.  Swallowing CancelledError here lets the engine
        loop continue after a manual close instead of being torn down.
        """
        opened = await self.open_valve()
        if not opened:
            # Valve was opened manually while we were preparing this
            # cycle — leave it alone and let the manual opener (or the
            # next tick) decide.
            return
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            # Manual close (or shutdown) cancelled the sleep.  The
            # closer has already recorded the close event, so just stop.
            return
        await self.close_valve()

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

    # ── overridable hooks ───────────────────────────────────────────
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


def make_default_controller() -> ValveController:
    """Convenience factory used by ``main.py``."""
    return ValveController(hardware=make_valve_hardware())

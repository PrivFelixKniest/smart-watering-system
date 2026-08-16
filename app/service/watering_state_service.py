"""Reconstruct the engine's watering state from persisted WaterTickEvent rows
so it survives restarts.

The engine (`smart_watering_system.engine.decide`) needs two pieces of
history to make correct decisions:
  * `last_watering` — when the valve was last opened (for the cadence gate).
  * `seconds_open_last_3_days` — total valve-open time in the last 3
    calendar days (for the budget gate).

Neither is stored explicitly. Both are reconstructed from the
`WaterTickEvent` log, which records one row per tick with `valve_open: bool`
and `created_at`. A "watering event" is a contiguous run of
`valve_open=True` rows; its duration is the gap from the first open tick
to the first following closed tick (or to `now` if the valve is still open).

This is the same pair-measurement used by
`water_consumption_service.calculate_usage_time`, applied over the
window the engine cares about.

Live valve loop integration
---------------------------
The live loop lives in `smart_watering_system.valve_controller.ValveController`.
It calls this function on each tick to reconstruct state from the
`WaterTickEvent` log, feeds it into `engine.decide`, and records every
valve transition as a new `WaterTickEvent` row.  Because every transition
is persisted, a restart loses nothing: this function reconstructs state
from the log on the next tick.  No in-memory state needs to be kept
between ticks.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database.models import WaterTickEvent, engine as db_engine
from smart_watering_system.engine import BUDGET_WINDOW_DAYS


def _open_durations(events: list[WaterTickEvent], now: datetime) -> list[tuple[datetime, float]]:
    """Return [(start_time, duration_seconds), ...] for each contiguous
    valve-open run in `events` (which must be sorted ascending by created_at).

    A run's duration is the gap from its first open tick to the first
    following closed tick. If the run is still open at the end of the list,
    its duration extends to `now`.
    """
    runs: list[tuple[datetime, float]] = []
    run_start: datetime | None = None

    for i, ev in enumerate(events):
        if ev.valve_open and run_start is None:
            run_start = ev.created_at
        elif not ev.valve_open and run_start is not None:
            duration = (ev.created_at - run_start).total_seconds()
            if duration > 0:
                runs.append((run_start, duration))
            run_start = None

    if run_start is not None:
        duration = (now - run_start).total_seconds()
        if duration > 0:
            runs.append((run_start, duration))

    return runs


def get_watering_state(db: Session, now: datetime | None = None):
    """Return (last_watering, seconds_open_last_3_days).

    `last_watering` is the start time of the most recent valve-open run,
    or None if the valve has never opened. `seconds_open_last_3_days` is
    the sum of open-run durations whose *start* falls within the last
    `BUDGET_WINDOW_DAYS` calendar days (midnight-aligned, matching the
    engine's own windowing in sim/simulator.py:73-75).
    """
    if now is None:
        now = datetime.now()

    # Pull everything from the 3-day window start onwards (plus a small
    # margin so we can see the run that may have started just before it).
    window_start = (now - timedelta(days=BUDGET_WINDOW_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    margin = timedelta(hours=25)
    fetch_from = window_start - margin

    events = (
        db.query(WaterTickEvent)
        .where(WaterTickEvent.created_at >= fetch_from)
        .order_by(WaterTickEvent.created_at.asc())
        .all()
    )

    runs = _open_durations(events, now)

    last_watering = runs[-1][0] if runs else None

    seconds_last_3d = 0.0
    for start, duration in runs:
        if start >= window_start:
            seconds_last_3d += duration

    return last_watering, seconds_last_3d


def get_watering_state_now() -> tuple[datetime | None, float]:
    """Convenience: reconstruct state against a fresh DB session and `now`."""
    with Session(db_engine) as db:
        return get_watering_state(db)

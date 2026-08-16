"""The watering decision: one function, no classes.

Given the current hour, the relevant weather readings, recent watering
history, and the user's watering_demand (0..100, 50 == sensible default),
return how many seconds to open the valve right now.  0 means "don't water".

Design goal: watering should be **stable and predictable**.  A given day
either gets watered or it doesn't, and if it does the valve opens at the
earliest good morning hour.  The decision does not flap hour-to-hour based
 on exactly when rain falls inside the forecast window.

The rules, in plain English:
  * Don't water at demand 0 (system off).
  * Only water in the morning (04:00-10:00) to limit evaporation and fungus.
  * Don't water if the soil is frozen or snow is on the ground.
  * Don't water if heavy rain is forecast in the morning itself.
  * Don't water if today is "too soon" after the last watering day.  The gap
    is measured in **calendar days** (not hours) so the watering time doesn't
    drift.  The gap shrinks with demand (50 -> 3 days, 100 -> 0 days).
  * Don't water if enough was already dispensed in the last 3 calendar days.
  * Otherwise water only when soil moisture drops below a demand-scaled
    threshold, for a duration that scales with demand *and* how parched the
    soil is.  At very high demand (>=85) multiple waterings per day are
    allowed, governed only by the morning window and the 3-day budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# ── Tunables ────────────────────────────────────────────────────────────────
MORNING_START = 4
MORNING_END = 10

FREEZE_SOIL_TEMP_C = 1.0       # below this, ground is frozen
SNOW_DEPTH_M = 0.01           # 1 cm of snow -> dormancy
HEAVY_RAIN_FORECAST_MM = 5.0  # skip if this much rain in the next 24 h
FORECAST_HOURS = 24

# Soil moisture (m3/m3, Open-Meteo's 1-3 cm layer).
MOISTURE_THRESHOLD_AT_50 = 0.20
MOISTURE_THRESHOLD_AT_100 = 0.35
WILT_MOISTURE = 0.10

# Duration scales with how dry the soil is.
MIN_DURATION_SEC = 20 * 60
MAX_DURATION_SEC = 60 * 60

# Deep-watering cadence (calendar-day based to avoid hour-drift).
# The base interval is a fixed function of demand, but it **shortens when
# the soil is very dry** — a stable signal that a hot spell is baking the
# lawn.  This lets a scorching week water every 1-2 days instead of waiting
# the full 3, while a cool damp week keeps the full interval.  Unlike the
# old daily-ET0 acceleration (which flapped with weather noise), soil
# dryness is a smoothed, stable signal.
#   demand 50 -> 3 days (base), 100 -> 0 days, 0 -> 6 days
#   soil near wilt -> interval roughly halved
MIN_INTERVAL_DAYS_AT_50 = 3.0
MIN_INTERVAL_DAYS_AT_100 = 0.0
MIN_INTERVAL_DAYS_AT_0 = 6.0
MIN_INTERVAL_FLOOR_DAYS = 1.0   # below demand ~85, never twice in one day
# When soil moisture drops to this fraction of the way from threshold to
# wilt, the interval starts shortening.  At wilt it's halved.
DRYNESS_ACCEL_START = 0.5      # 50% dryness -> begin shortening
DRYNESS_ACCEL_MAX = 0.5        # at full dryness, multiply interval by (1 - this)

# Rolling 3-calendar-day water budget.
BUDGET_WINDOW_DAYS = 3
BUDGET_MIN_AT_50 = 90 * 60
BUDGET_MIN_AT_100 = 480 * 60


# ── Decision output ──────────────────────────────────────────────────────────
# Reason strings for a Decision.  Kept as plain constants (not an enum) so
# they render directly in templates / JSON without `.value` lookup.
REASON_OFF = "off"
REASON_MORNING_ONLY = "morning only"
REASON_FROZEN = "frozen"
REASON_SNOW = "snow"
REASON_RAIN_FORECAST = "rain forecast"
REASON_CADENCE = "cadence"
REASON_BUDGET = "budget"
REASON_SOIL_MOIST = "soil moist"
REASON_WATERING = "watering"


@dataclass
class Decision:
    """Result of a single engine tick.

    `seconds` is the valve-open time (0 == don't water); `reason` explains
    *why* the engine decided the way it did — useful for the forecast view
    and for debugging.  When `seconds > 0`, `reason` is always REASON_WATERING.
    """
    seconds: float
    reason: str


def moisture_threshold(demand: float) -> float:
    t = MOISTURE_THRESHOLD_AT_50
    t += (MOISTURE_THRESHOLD_AT_100 - MOISTURE_THRESHOLD_AT_50) * max(0.0, (demand - 50) / 50.0)
    return t


def min_interval_days(demand: float, dryness: float = 0.0) -> float:
    """Minimum *calendar days* between watering days.

    Base is a fixed function of demand.  When the soil is very dry
    (`dryness` approaching 1, i.e. soil near wilt), the interval shortens
    so a scorching week waters sooner.  `dryness` is the same 0..1 value
    the duration uses: 0 = just below threshold, 1 = at wilt.
    """
    if demand <= 50:
        base = MIN_INTERVAL_DAYS_AT_50 + (MIN_INTERVAL_DAYS_AT_0 - MIN_INTERVAL_DAYS_AT_50) * (1.0 - demand / 50.0)
    else:
        base = MIN_INTERVAL_DAYS_AT_50 + (MIN_INTERVAL_DAYS_AT_100 - MIN_INTERVAL_DAYS_AT_50) * ((demand - 50) / 50.0)
    # Shorten the interval when the soil is parched.  Below DRYNESS_ACCEL_START
    # the soil is only mildly dry — keep the full interval.  Above it, scale
    # linearly down so at full dryness the interval is halved.
    if dryness > DRYNESS_ACCEL_START:
        shrink = (dryness - DRYNESS_ACCEL_START) / (1.0 - DRYNESS_ACCEL_START)
        base *= 1.0 - DRYNESS_ACCEL_MAX * shrink
    floor = 0.0 if demand >= 85.0 else MIN_INTERVAL_FLOOR_DAYS
    return max(floor, base)


def budget_seconds(demand: float) -> float:
    b = BUDGET_MIN_AT_50
    b += (BUDGET_MIN_AT_100 - BUDGET_MIN_AT_50) * max(0.0, (demand - 50) / 50.0)
    return b


def _calendar_days_between(a: datetime, b: datetime) -> int:
    """Whole calendar days from date(a) to date(b).  Same-day -> 0."""
    return (b.date() - a.date()).days


def decide(
    now: datetime,
    hourly_times: list[datetime],
    precipitation: list[float],
    soil_temperature_0cm: list[float],
    soil_moisture_1_to_3cm: list[float],
    snow_depth: list[float],
    watering_demand: float,
    last_watering: datetime | None = None,
    seconds_open_last_3_days: float = 0.0,
    et0_fao_evapotranspiration: list[float] | None = None,
) -> Decision:
    """Return a Decision for this tick.  `seconds == 0` means don't water;
    `reason` explains why (or "watering" when seconds > 0).

    The decision is designed to be **stable within a day**: if the engine
    decides "water today", it opens the valve at the first morning hour
    that isn't blocked by a rain forecast, and does not re-evaluate later
    that same morning (the interval/budget gates see the morning's own
    watering and suppress the rest of the day).  This keeps the watering
    time from drifting or flapping hour to hour.
    """
    # 1. Off
    if watering_demand <= 0:
        return Decision(0.0, REASON_OFF)

    # 2. Morning window only
    hour = now.hour
    if hour < MORNING_START or hour >= MORNING_END:
        return Decision(0.0, REASON_MORNING_ONLY)

    # Index of the most recent sample.
    idx = -1
    for i, t in enumerate(hourly_times):
        if t <= now:
            idx = i
        else:
            break
    if idx < 0:
        return Decision(0.0, REASON_MORNING_ONLY)

    # 3. Frozen ground / snow -> dormancy
    if soil_temperature_0cm[idx] <= FREEZE_SOIL_TEMP_C:
        return Decision(0.0, REASON_FROZEN)
    if snow_depth[idx] >= SNOW_DEPTH_M:
        return Decision(0.0, REASON_SNOW)

    # 4. Heavy rain in the forecast window -> skip this hour
    horizon = now + timedelta(hours=FORECAST_HOURS)
    upcoming_rain = 0.0
    for i in range(idx, len(hourly_times)):
        if hourly_times[i] > horizon:
            break
        upcoming_rain += precipitation[i]
    if upcoming_rain >= HEAVY_RAIN_FORECAST_MM:
        return Decision(0.0, REASON_RAIN_FORECAST)

    # 5. Minimum interval between watering *days* (calendar-day based).
    #    The interval shortens when the soil is very dry so a hot week
    #    waters sooner than a cool week.
    moisture = soil_moisture_1_to_3cm[idx]
    threshold = moisture_threshold(watering_demand)
    dryness = (threshold - moisture) / max(threshold - WILT_MOISTURE, 1e-6)
    dryness = max(0.0, min(dryness, 1.0))
    if last_watering is not None:
        days_since = _calendar_days_between(last_watering, now)
        interval = min_interval_days(watering_demand, dryness)
        if days_since < interval:
            return Decision(0.0, REASON_CADENCE)

    # 6. Rolling 3-day water budget: skip if enough was dispensed recently.
    if seconds_open_last_3_days >= budget_seconds(watering_demand):
        return Decision(0.0, REASON_BUDGET)

    # 7. Soil dry enough?  (already computed above)
    if moisture > threshold:
        return Decision(0.0, REASON_SOIL_MOIST)

    # 8. Water: duration scales with demand AND how parched the soil is.
    demand_factor = watering_demand / 50.0
    duration = MIN_DURATION_SEC + (MAX_DURATION_SEC - MIN_DURATION_SEC) * dryness
    return Decision(duration * demand_factor, REASON_WATERING)

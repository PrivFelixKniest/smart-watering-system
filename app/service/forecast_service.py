"""Simulate the watering engine over the next 7 days for the selected
profile's location and watering_demand, and compile the per-day results
for the forecast table.

This is a pure simulation harness — no decision logic lives here.  The
engine (`smart_watering_system.engine.decide`) is the single source of
truth for every watering decision and the reason behind it.  This module
only advances a soil-moisture bucket (so the engine's feedback loop works
across days), feeds each hour into `decide`, and collects the results.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from clients.geocoding_open_meteo import geocoding_open_meteo_api
from clients.open_meteo import open_meteo_api
from service.shared.selected_profile_service import get_selected_profile
from service.watering_state_service import get_watering_state
from smart_watering_system.engine import BUDGET_WINDOW_DAYS, REASON_MORNING_ONLY, decide

# Same soil-moisture bucket model as the simulator so the engine's feedback
# loop (deep-watering cadence + 3-day budget) is exercised realistically.
LAYER_DEPTH_MM = 20.0
WATER_RATE_MM_PER_HOUR = 5.0
FIELD_CAPACITY = 0.30
WILT = 0.10
KC = 0.85


async def get_forecast_plan(db: Session, days: int = 7):
    """Return (city, list_of_day_dicts).

    Each day dict: {date, weekday, water_minutes, rain_mm, temp_avg,
    moisture_end, skip_reason}.  `skip_reason` is None when the engine
    watered that day, else the reason string from the engine's Decision
    for the last morning hour that was evaluated.
    """
    profile = await get_selected_profile(db)
    geocodes = await geocoding_open_meteo_api.search(profile.city)
    geocode = geocodes.results[0]
    weather = await open_meteo_api.get_forecast(
        geocode.latitude, geocode.longitude, forecast_days=days
    )

    times = weather.hourly.time
    precipitation = weather.hourly.precipitation
    soil_temp = weather.hourly.soil_temperature_0cm
    soil_moist = list(weather.hourly.soil_moisture_1_to_3cm)
    snow_depth = weather.hourly.snow_depth
    et0 = weather.hourly.et0_fao_evapotranspiration

    moisture = soil_moist[0] if soil_moist and soil_moist[0] is not None else FIELD_CAPACITY
    # Seed the engine state from persisted history so the forecast behaves
    # as if the system had been running continuously.  `seeded_last_watering`
    # holds the most recent real watering before the forecast window; it is
    # used until a forecast-period watering supersedes it.  `seeded_budget`
    # is the valve-open time already consumed in the rolling 3-day window;
    # it is added to whatever the forecast itself dispenses.
    now_start = times[0] if times else datetime.now()
    seeded_last_watering, seeded_budget = get_watering_state(db, now=now_start)
    events: list[tuple] = []  # (timestamp, open_seconds) — forecast-only
    days_out = min(days, len(times) // 24)
    # Mirrors ValveController: while the valve is notionally open, skip
    # decide() — no overlapping commands, no spurious second watering at
    # demand >= 85 that the real controller would never produce.
    valve_open_until: datetime | None = None

    day_results = []
    for day in range(days_out):
        day_water_seconds = 0.0
        last_skip = None
        watered_today = False
        for h in range(24):
            idx = day * 24 + h
            if idx >= len(times):
                break
            now = times[idx]

            # Advance the moisture bucket with weather only.
            moisture -= et0[idx] * KC / LAYER_DEPTH_MM
            moisture += precipitation[idx] / LAYER_DEPTH_MM
            moisture = max(WILT * 0.8, min(moisture, FIELD_CAPACITY))
            soil_moist[idx] = moisture

            # ValveController guard: don't call decide() while the valve
            # is still open from a previous decision this morning.
            if valve_open_until is not None and now < valve_open_until:
                continue

            # Use the most recent of: seeded real watering, or a forecast
            # watering that happened during this simulation.
            last_watering = events[-1][0] if events else seeded_last_watering
            window_start = (now - timedelta(days=BUDGET_WINDOW_DAYS)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # Rolling 3-day budget = pre-forecast consumption (if it still
            # falls inside the window) + forecast-period consumption.
            budget_from_seed = seeded_budget if seeded_last_watering is not None and seeded_last_watering >= window_start else 0.0
            seconds_last_3d = budget_from_seed + sum(s for t, s in events if t >= window_start)

            decision = decide(
                now=now,
                hourly_times=times,
                precipitation=precipitation,
                soil_temperature_0cm=soil_temp,
                soil_moisture_1_to_3cm=soil_moist,
                snow_depth=snow_depth,
                watering_demand=profile.watering_demand,
                last_watering=last_watering,
                seconds_open_last_3_days=seconds_last_3d,
                et0_fao_evapotranspiration=et0,
            )

            if decision.seconds > 0:
                events.append((now, decision.seconds))
                day_water_seconds += decision.seconds
                mm_applied = (decision.seconds / 3600.0) * WATER_RATE_MM_PER_HOUR
                moisture = min(FIELD_CAPACITY, moisture + mm_applied / LAYER_DEPTH_MM)
                soil_moist[idx] = moisture
                watered_today = True
                last_skip = None
                # Mirror ValveController: the valve is now busy until this
                # watering completes.  Subsequent ticks within that window
                # skip decide() entirely (see the guard above).
                valve_open_until = now + timedelta(seconds=decision.seconds)
            elif not watered_today and decision.reason != REASON_MORNING_ONLY:
                # Record the engine's reason for the last non-trivial skip
                # of the morning.  "morning only" is the default outside the
                # 04:00-10:00 window and carries no information, so ignore it.
                last_skip = decision.reason

        s = day * 24
        e = min(s + 24, len(times))
        day_temps = soil_temp[s:e]
        day_rain = sum(precipitation[s:e])
        day_results.append({
            "date": times[s].strftime("%d.%m"),
            "weekday": times[s].strftime("%a"),
            "water_minutes": round(day_water_seconds / 60.0),
            "water_seconds": day_water_seconds,
            "rain_mm": round(day_rain, 1),
            "temp_avg": round(sum(day_temps) / len(day_temps), 1) if day_temps else 0.0,
            "moisture_end": round(soil_moist[e - 1], 3),
            "skip_reason": last_skip,
        })

    return profile.city, day_results

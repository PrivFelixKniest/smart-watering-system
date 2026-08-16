"""Deterministic synthetic weather scenarios for the simulator.

Each scenario produces hour-by-hour arrays for one location/season.  ET0 is
derived from air temperature (a simplified Hargreaves relation: ET0 scales
with the daylight temperature above 0°C), so a hot climate genuinely dries
the soil faster than a cool one — no separate et0_peak knob to keep in sync.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

# Open-Meteo soil-moisture units are volumetric m3/m3.
# Loam: ~0.10 wilt, ~0.30 field capacity, ~0.45 saturated.
WILT = 0.10
FIELD_CAPACITY = 0.30

# ET0 scaling: Hargreaves-like quadratic relation (ET0 ∝ temp²).
# A 40°C midday hour produces ~1.9 mm ET0; a 15°C hour ~0.27 mm — a 7x
# ratio, so a hot summer dries the soil in under a day while a cool spring
# takes nearly a week.  Only temp above 0°C contributes.
ET0_COEFF = 0.0012   # mm / (°C² * daylight-hour)


@dataclass
class Scenario:
    name: str
    lat: float
    start: datetime
    days: int
    air_temp_c: float           # daily mean
    air_amp: float              # diurnal amplitude
    soil_temp_c: float          # daily mean
    snow_depth_m: float
    rain_prob: float            # chance of a rainy day
    start_moisture: float       # initial soil moisture


SCENARIOS: dict[str, Scenario] = {
    "phoenix_summer": Scenario(
        "Phoenix July (hot dry)", 33.4,
        datetime(2024, 7, 1), 14, 33.0, 8.0, 30.0, 0.0, 0.05, 0.12,
    ),
    "heatwave": Scenario(
        "Heatwave (extreme 40°C)", 33.4,
        datetime(2024, 7, 1), 14, 40.0, 10.0, 37.0, 0.0, 0.0, 0.12,
    ),
    "monsoon": Scenario(
        "Monsoon (hot + very rainy)", 25.0,
        datetime(2024, 7, 1), 14, 30.0, 6.0, 28.0, 0.0, 0.85, 0.28,
    ),
    "berlin_spring": Scenario(
        "Berlin April (cool damp)", 52.5,
        datetime(2024, 4, 1), 14, 11.0, 6.0, 9.0, 0.0, 0.30, 0.22,
    ),
    "sydney_summer": Scenario(
        "Sydney January (warm)", -33.9,
        datetime(2024, 1, 1), 14, 24.0, 6.0, 23.0, 0.0, 0.20, 0.20,
    ),
    "reykjavik_winter": Scenario(
        "Reykjavík January (snow/frozen)", 64.1,
        datetime(2024, 1, 1), 14, 1.0, 3.0, -1.0, 0.05, 0.40, 0.25,
    ),
    "london_summer": Scenario(
        "London June (mild wet)", 51.5,
        datetime(2024, 6, 1), 14, 16.0, 5.0, 15.0, 0.0, 0.40, 0.22,
    ),
    "tropics_wet": Scenario(
        "Tropics wet season", 0.0,
        datetime(2024, 3, 1), 14, 27.0, 2.0, 26.0, 0.0, 0.60, 0.32,
    ),
}


def generate(s: Scenario) -> dict:
    """Build the hour-by-hour arrays the engine consumes."""
    rng = random.Random(sum(ord(c) for c in s.name) + s.days)
    times, precip, soil_temp, soil_moist, snow, et0 = [], [], [], [], [], []

    moisture = s.start_moisture
    LAYER_DEPTH_MM = 20.0  # 1-3 cm layer
    KC = 0.85

    for day in range(s.days):
        daily_rain = rng.random() < s.rain_prob
        if daily_rain:
            rain_mm = rng.uniform(8.0, 20.0)       # heavy monsoon downpour
            rain_duration = rng.randint(3, 6)      # spread over several hours
            rain_hour = rng.randint(0, 23 - rain_duration)
        else:
            rain_mm = 0.0
            rain_duration = 0
            rain_hour = -1
        per_hour_rain = rain_mm / rain_duration if rain_duration > 0 else 0.0
        for h in range(24):
            t = s.start + timedelta(days=day, hours=h)
            diurnal = -math.cos((h - 4) / 24.0 * 2 * math.pi)
            air = s.air_temp_c + s.air_amp * diurnal
            st = s.soil_temp_c + s.air_amp * 0.4 * diurnal
            daylight = max(0.0, math.sin((h - 6) / 24.0 * 2 * math.pi))
            # ET0 derived from temperature: hotter hour -> much more
            # evaporation (quadratic, like real Hargreaves).  Only daylight
            # hours produce meaningful ET0 (daylight factor).
            temp_above_zero = max(0.0, air)
            e = ET0_COEFF * temp_above_zero * temp_above_zero * daylight
            e *= (1.0 + 0.05 * rng.gauss(0, 1))
            e = max(0.0, e)
            r = per_hour_rain if (daily_rain and rain_hour <= h < rain_hour + rain_duration) else 0.0
            # Drain/refill soil moisture bucket
            moisture -= e * KC / LAYER_DEPTH_MM
            moisture += r / LAYER_DEPTH_MM
            moisture = max(WILT * 0.8, min(moisture, FIELD_CAPACITY))
            times.append(t)
            precip.append(round(r, 2))
            soil_temp.append(round(st, 2))
            soil_moist.append(round(moisture, 3))
            snow.append(s.snow_depth_m)
            et0.append(round(e, 3))

    return {
        "times": times,
        "precipitation": precip,
        "soil_temperature_0cm": soil_temp,
        "soil_moisture_1_to_3cm": soil_moist,
        "snow_depth": snow,
        "et0": et0,
    }

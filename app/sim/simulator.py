"""Minimalist command-line simulator + visualizer for the watering engine.

Runs the engine hour-by-hour across several weather scenarios, opens/closes
a virtual valve, and prints a per-day chart showing when the valve was on.
It tracks watering history (last watering time + seconds open in the last 3
days) and feeds it back into the engine so the deep-watering cadence and
3-day budget rules are exercised.

Usage (from app/):
    python -m sim.simulator
    python -m sim.simulator --scenario berlin_spring --days 14 --demand 50
    python -m sim.simulator --all --demand 75
    python -m sim.simulator --forecast berlin --demand 75      # real saved forecast
    python -m sim.simulator --all-forecasts --demand 75        # all saved forecasts
    python -m sim.simulator --forecast=LIST                    # list saved forecasts
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from sim.scenarios import SCENARIOS, Scenario, generate
from sim.forecast_loader import load_forecast, list_available
from smart_watering_system.engine import BUDGET_WINDOW_DAYS, decide


def run(scenario: Scenario | None, weather: dict, days: int, demand: float):
    """Return (grid, day_stats) where grid is valve-on/off booleans [day][hour]
    and day_stats is a list of dicts with per-day weather + watering info.

    Soil moisture is modeled as a single running bucket advanced hour-by-hour:
    it drains with ET0, recharges with rain, and recharges with valve water.
    This makes the feedback loop work — a deep watering actually raises
    moisture for the following hours, so the engine correctly waits a few
    days before watering again.  A hot climate drains the bucket faster than
    a cool one, so it waters more often and longer.
    """
    grid: list[list[bool]] = []
    day_stats: list[dict] = []
    events: list[tuple] = []  # (timestamp, open_seconds)

    # Soil-moisture bucket (m3/m3).  Same model as the scenario generator so
    # the two stay consistent, but this one also sees the effect of watering.
    LAYER_DEPTH_MM = 20.0
    WATER_RATE_MM_PER_HOUR = 5.0
    FIELD_CAPACITY = 0.30
    WILT = 0.10
    KC = 0.85
    moisture = weather["soil_moisture_1_to_3cm"][0]

    # We build a mutable moisture array the engine reads from; each hour we
    # advance the bucket and overwrite the slot so the engine sees the live
    # value rather than the pre-computed one.
    soil_moisture = [0.0] * len(weather["soil_moisture_1_to_3cm"])

    for day in range(days):
        row = [False] * 24
        day_water_seconds = 0.0
        for h in range(24):
            idx = day * 24 + h
            now = weather["times"][idx]

            # Advance the moisture bucket for this hour using the
            # pre-computed ET0 and rain from the scenario (weather happens
            # regardless of watering).
            et0 = weather["et0"][idx]
            rain = weather["precipitation"][idx]
            moisture -= et0 * KC / LAYER_DEPTH_MM
            moisture += rain / LAYER_DEPTH_MM
            moisture = max(WILT * 0.8, min(moisture, FIELD_CAPACITY))
            soil_moisture[idx] = moisture

            last_watering = events[-1][0] if events else None
            # 3-calendar-day window: from midnight 3 days ago to now.
            # Using midnight boundaries (not `now - 3 days`) avoids the
            # watering time drifting later and later each day.
            window_start = (now - timedelta(days=BUDGET_WINDOW_DAYS)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            seconds_last_3d = sum(s for t, s in events if t >= window_start)

            decision = decide(
                now=now,
                hourly_times=weather["times"],
                precipitation=weather["precipitation"],
                soil_temperature_0cm=weather["soil_temperature_0cm"],
                soil_moisture_1_to_3cm=soil_moisture,
                snow_depth=weather["snow_depth"],
                watering_demand=demand,
                last_watering=last_watering,
                seconds_open_last_3_days=seconds_last_3d,
                et0_fao_evapotranspiration=weather["et0"],
            )
            seconds = decision.seconds
            if seconds > 0:
                events.append((now, seconds))
                day_water_seconds += seconds
                # Recharge the bucket by the water applied.
                mm_applied = (seconds / 3600.0) * WATER_RATE_MM_PER_HOUR
                moisture = min(FIELD_CAPACITY, moisture + mm_applied / LAYER_DEPTH_MM)
                soil_moisture[idx] = moisture
                # Mark the watering hours (rounded up) on the chart.
                hours_on = max(1, int(round(seconds / 3600.0)))
                for ho in range(hours_on):
                    if h + ho < 24:
                        row[h + ho] = True
        grid.append(row)

        s = day * 24
        e = s + 24
        temps = weather["soil_temperature_0cm"][s:e]
        rains = weather["precipitation"][s:e]
        day_stats.append({
            "temp_avg": sum(temps) / len(temps),
            "temp_min": min(temps),
            "temp_max": max(temps),
            "rain_mm": sum(rains),
            "moisture_end": soil_moisture[e - 1],
            "water_seconds": day_water_seconds,
        })
    return grid, day_stats


def render(scenario_name: str, grid: list[list[bool]], day_stats: list[dict], demand: float) -> None:
    print(f"\n=== {scenario_name}  (demand={demand}) ===")
    # Hour header: 00..23, one cell per hour (each 3 chars wide: "00 ", "01 ").
    print("day  " + " ".join(f"{h:02d}" for h in range(24)) + "   temp   rain  soil   water")
    print("     " + "-" * 70)
    for day_idx, row in enumerate(grid):
        label = f"{day_idx + 1:>2}  "
        # Each cell padded to 2 chars + space so dots/hashtags align under "00".."23".
        line = " ".join(("##" if on else " .") for on in row)
        st = day_stats[day_idx]
        water_min = st["water_seconds"] / 60.0
        print(
            f"{label}{line} "
            f"{st['temp_avg']:4.1f}C "
            f"{st['rain_mm']:4.1f}mm "
            f"{st['moisture_end']:.2f} "
            f"{water_min:4.0f}min"
        )
    # summary
    total_hours = sum(sum(r) for r in grid)
    water_days = sum(1 for r in grid if any(r))
    total_min = sum(s["water_seconds"] for s in day_stats) / 60.0
    print(f"     -> {total_hours} valve-hours, {total_min:.0f} min total "
          f"over {water_days}/{len(grid)} days")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--scenario", "-s", default="berlin_spring",
                     choices=list(SCENARIOS.keys()),
                     help="synthetic scenario to run (default: berlin_spring)")
    src.add_argument("--forecast", "-f",
                     help="saved real forecast name (e.g. 'berlin') or path; "
                          "use --forecast=LIST to list available")
    p.add_argument("--all", action="store_true",
                   help="run every synthetic scenario (ignored if --forecast)")
    p.add_argument("--all-forecasts", action="store_true",
                   help="run every saved forecast in sim/forecasts/")
    p.add_argument("--days", type=int, default=14,
                   help="number of days to simulate (capped to forecast length)")
    p.add_argument("--demand", type=float, default=50.0)
    args = p.parse_args()

    # Build list of (label, weather_dict) to run.
    runs: list[tuple[str, dict]] = []
    if args.forecast:
        if args.forecast == "LIST":
            avail = list_available()
            print("saved forecasts in sim/forecasts/:")
            for n in avail:
                print(f"  {n}")
            if not avail:
                print("  (none — run: python -m sim.fetch_forecasts --save)")
            return
        runs = [(args.forecast, load_forecast(args.forecast))]
    elif args.all_forecasts:
        names = list_available()
        if not names:
            print("no saved forecasts — run: python -m sim.fetch_forecasts --save")
            return
        runs = [(n, load_forecast(n)) for n in names]
    elif args.all:
        for name, sc in SCENARIOS.items():
            runs.append((name, generate(sc)))
    else:
        sc = SCENARIOS[args.scenario]
        runs = [(args.scenario, generate(sc))]

    for label, weather in runs:
        # Cap days to the data we actually have (24h per day).
        max_days = len(weather["times"]) // 24
        days = min(args.days, max_days)
        grid, day_stats = run(None, weather, days, args.demand)
        render(label, grid, day_stats, args.demand)


if __name__ == "__main__":
    main()

"""Fetch real Open-Meteo forecasts for several world locations and print them
in a format that drops straight into sim/scenarios.py / the simulator.

The fields requested match exactly what the watering engine consumes
(see app/clients/open_meteo/open_meteo_api.py), so a pasted forecast is a
realistic stand-in for the synthetic Scenario.generate() output.

Usage (from app/):
    python -m sim.fetch_forecasts                    # all preset locations
    python -m sim.fetch_forecasts --loc berlin        # one location
    python -m sim.fetch_forecasts --lat 52.5 --lon 13.4 --name custom
    python -m sim.fetch_forecasts --days 7           # override forecast horizon (1-16)

Output: for each location, prints a compact JSON block containing the
location name, coordinates, timezone, and the hourly arrays
(times, precipitation, soil_temperature_0cm, soil_moisture_1_to_3cm,
snow_depth, et0_fao_evapotranspiration, temperature_2m).  Paste a block into
the chat and it can be turned into a Scenario / weather dict for the engine.

No project imports are required — only the Python 3.11+ standard library
(urllib + json), so this script runs even before the app's deps are
installed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

# Default directory for saved forecasts (relative to app/).
DEFAULT_OUT_DIR = os.path.join(os.path.dirname(__file__), "forecasts")

# Same endpoint and hourly variable list as open_meteo_api.get_forecast().
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "et0_fao_evapotranspiration",
    "soil_temperature_0cm",
    "soil_moisture_1_to_3cm",
    "snow_depth",
]

# Preset locations spanning the climates the synthetic scenarios already
# cover, so fetched forecasts are directly comparable.  lat/lon only — the
# script fills in the rest from the live API.
PRESET_LOCATIONS: dict[str, tuple[float, float]] = {
    "phoenix":      (33.45, -112.07),   # hot dry desert summer
    "heatwave":     (33.45, -112.07),   # same point; pick a heatwave week
    "monsoon":      (19.07, 72.87),     # Mumbai wet season
    "berlin":       (52.52, 13.40),    # cool damp spring
    "sydney":       (-33.87, 151.21),  # warm summer
    "reykjavik":    (64.15, -21.94),   # cold / snow / frozen
    "london":       (51.51, -0.13),    # mild wet
    "tropics":      (0.0, -78.5),      # Quito, wet equatorial
    "singapore":    (1.35, 103.82),    # hot humid equatorial
}


def fetch_forecast(name: str, lat: float, lon: float, days: int, timeout: float = 10.0) -> dict:
    """Fetch one forecast from Open-Meteo and return a compact dict."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "forecast_days": days,
        "timezone": "auto",
    }
    url = OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))

    hourly = data["hourly"]
    times = [datetime.fromisoformat(t) for t in hourly["time"]]

    block = {
        "name": name,
        "latitude": round(data["latitude"], 4),
        "longitude": round(data["longitude"], 4),
        "timezone": data.get("timezone", "UTC"),
        "elevation": data.get("elevation"),
        "units": data.get("hourly_units", {}),
        "hourly": {
            "times":           [t.isoformat() for t in times],
            "temperature_2m":  hourly["temperature_2m"],
            "precipitation":   hourly["precipitation"],
            "precipitation_probability": hourly.get("precipitation_probability"),
            "et0_fao_evapotranspiration": hourly["et0_fao_evapotranspiration"],
            "soil_temperature_0cm":      hourly["soil_temperature_0cm"],
            "soil_moisture_1_to_3cm":    hourly["soil_moisture_1_to_3cm"],
            "snow_depth":                hourly["snow_depth"],
        },
    }
    return block


def summarize(block: dict) -> str:
    """One-line human summary printed before the JSON block."""
    h = block["hourly"]
    n = len(h["times"])
    temps = [t for t in h["temperature_2m"] if t is not None]
    rain = sum(r for r in h["precipitation"] if r is not None)
    moist = [m for m in h["soil_moisture_1_to_3cm"] if m is not None]
    snow = [s for s in h["snow_depth"] if s is not None]
    t_min = min(temps) if temps else float("nan")
    t_max = max(temps) if temps else float("nan")
    m_avg = sum(moist) / len(moist) if moist else float("nan")
    snow_max = max(snow) if snow else 0.0
    return (f"{n}h  temp {t_min:.1f}..{t_max:.1f}C  rain {rain:.1f}mm  "
            f"soil_mois_avg {m_avg:.3f}  snow_max {snow_max:.2f}m")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--loc", "-l", choices=list(PRESET_LOCATIONS.keys()),
                   help="preset location to fetch (default: all presets)")
    p.add_argument("--lat", type=float, help="custom latitude (with --lon)")
    p.add_argument("--lon", type=float, help="custom longitude (with --lat)")
    p.add_argument("--name", default="custom", help="label for custom --lat/--lon fetch")
    p.add_argument("--days", type=int, default=3, help="forecast horizon in days (1-16, default 3)")
    p.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout seconds")
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 = compact)")
    p.add_argument("--save", action="store_true",
                   help=f"write each forecast to <out-dir>/<name>.json (default out-dir: {DEFAULT_OUT_DIR})")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                   help=f"directory for --save (default: {DEFAULT_OUT_DIR})")
    p.add_argument("--quiet", action="store_true", help="suppress JSON to stdout (use with --save)")
    args = p.parse_args()

    if args.days < 1 or args.days > 16:
        p.error("--days must be in 1..16")

    # Build the list of (name, lat, lon) to fetch.
    if args.lat is not None or args.lon is not None:
        if args.lat is None or args.lon is None:
            p.error("--lat and --lon must be given together")
        targets = [(args.name, args.lat, args.lon)]
    elif args.loc is not None:
        lat, lon = PRESET_LOCATIONS[args.loc]
        targets = [(args.loc, lat, lon)]
    else:
        targets = [(name, lat, lon) for name, (lat, lon) in PRESET_LOCATIONS.items()]

    failures = 0
    for name, lat, lon in targets:
        print(f"\n### {name}  ({lat:.2f}, {lon:.2f})", file=sys.stderr)
        try:
            block = fetch_forecast(name, lat, lon, args.days, timeout=args.timeout)
        except Exception as exc:  # noqa: BLE001 - want to keep going on net errors
            failures += 1
            print(f"  ERROR: {exc}", file=sys.stderr)
            continue
        print(f"  {summarize(block)}", file=sys.stderr)
        if args.save:
            os.makedirs(args.out_dir, exist_ok=True)
            path = os.path.join(args.out_dir, f"{name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(block, f, indent=2, ensure_ascii=False)
            print(f"  saved -> {path}", file=sys.stderr)
        if not args.quiet:
            indent = args.indent if args.indent > 0 else None
            print(json.dumps(block, indent=indent, ensure_ascii=False))

    if failures:
        sys.stderr.write(f"\n{failures} fetch(es) failed\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

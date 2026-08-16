"""Load saved Open-Meteo forecasts (from fetch_forecasts.py --save) into the
weather dict shape the simulator/engine consumes.

The engine wants a dict with keys:
    times, precipitation, soil_temperature_0cm, soil_moisture_1_to_3cm,
    snow_depth, et0

Saved forecast JSON has hourly.{times, precipitation, soil_temperature_0cm,
soil_moisture_1_to_3cm, snow_depth, et0_fao_evapotranspiration, ...} with
iso strings; this module reshapes and parses times to datetimes.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

# Same default as fetch_forecasts.py --out-dir.
DEFAULT_FORECAST_DIR = os.path.join(os.path.dirname(__file__), "forecasts")


def load_forecast(name_or_path: str, forecast_dir: str = DEFAULT_FORECAST_DIR) -> dict:
    """Load one saved forecast by name (e.g. 'berlin') or by file path.

    Returns a dict shaped for simulator.run() / engine.decide().
    """
    if os.path.exists(name_or_path):
        path = name_or_path
    else:
        path = os.path.join(forecast_dir, f"{name_or_path}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"no saved forecast for {name_or_path!r} (looked for {path})"
            )

    with open(path, "r", encoding="utf-8") as f:
        block = json.load(f)

    h = block["hourly"]
    times = [datetime.fromisoformat(t) for t in h["times"]]
    return {
        "name": block.get("name", os.path.basename(path)),
        "latitude": block["latitude"],
        "longitude": block["longitude"],
        "timezone": block.get("timezone", "UTC"),
        "times": times,
        "precipitation": h["precipitation"],
        "soil_temperature_0cm": h["soil_temperature_0cm"],
        "soil_moisture_1_to_3cm": h["soil_moisture_1_to_3cm"],
        "snow_depth": h["snow_depth"],
        "et0": h["et0_fao_evapotranspiration"],
    }


def list_available(forecast_dir: str = DEFAULT_FORECAST_DIR) -> list[str]:
    """Return names of saved forecasts (without .json)."""
    if not os.path.isdir(forecast_dir):
        return []
    return sorted(
        f[:-5] for f in os.listdir(forecast_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(forecast_dir, f))
    )

"""Application configuration loaded from environment / .env file.

Environment variables can be set in the shell or in an ``.env`` file at
the app root (``app/.env``).  The file is loaded once on import via
``python-dotenv``; shell variables take precedence over file values.

Valve / GPIO
------------
VALVE_GPIO_PIN      BCM pin number driving the relay/solenoid.
                    Default: 17 (physical pin 11).

VALVE_ACTIVE_HIGH   ``true`` (default) — relay activates on HIGH.
                    ``false``               — relay activates on LOW
                    (common for cheap active-low relay modules).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env from the app root (app/.env) once at import time.
load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


VALVE_GPIO_PIN: int = int(os.environ.get("VALVE_GPIO_PIN", "17"))
VALVE_ACTIVE_HIGH: bool = _get_bool("VALVE_ACTIVE_HIGH", True)

"""GPIO / valve hardware abstraction.

On a Raspberry Pi this uses ``gpiozero.OutputDevice`` to drive a relay
or solenoid on a configurable BCM pin.  On any other platform (dev
machines, the simulator, non-Pi servers) it falls back to a mock that
just sleeps for the requested duration — no hardware touched, but the
timing and event logging behave identically so the rest of the system
can't tell the difference.

Raspberry Pi setup
------------------
    pip install -r requirements.txt
    cp .env.example .env   # then edit pin / active-high as needed

Configuration is loaded from ``app/.env`` (or the shell environment)
by ``config.py`` — see ``.env.example`` for available keys.

Usage (from ``main.py``)::

    opener = make_valve_opener()
    await opener(seconds=1200)   # opens the valve for 20 minutes
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import config

log = logging.getLogger(__name__)


def make_valve_opener() -> Callable[[float], Awaitable[None]]:
    """Return an async valve opener for the current platform.

    On a real Raspberry Pi (detected via ``/proc/device-tree/compatible``)
    this constructs a ``gpiozero.OutputDevice`` once and returns a closure
    that drives it.  On every other platform it returns a mock that just
    sleeps — no GPIO, but the timing and event log are identical.
    """
    if _is_raspberry_pi():
        return _make_pi_valve_opener()
    log.warning("not running on a Raspberry Pi — using mock valve opener")
    return _mock_valve_opener


def _is_raspberry_pi() -> bool:
    try:
        with open("/proc/device-tree/compatible", "r") as f:
            return "raspberrypi" in f.read()
    except OSError:
        return False


def _make_pi_valve_opener() -> Callable[[float], Awaitable[None]]:
    """Build a closure around a single ``gpiozero.OutputDevice``."""
    import gpiozero

    pin = config.VALVE_GPIO_PIN
    active_high = config.VALVE_ACTIVE_HIGH
    device = gpiozero.OutputDevice(pin, active_high=active_high)
    log.info(
        "GPIO valve opener initialized on BCM pin %d (active_high=%s)",
        pin,
        active_high,
    )

    async def opener(seconds: float) -> None:
        try:
            device.on()
            log.info("valve OPEN for %.0f seconds (BCM %d)", seconds, pin)
            await asyncio.sleep(seconds)
        finally:
            # .off() is a fast synchronous pin write — safe to call
            # directly, even during task cancellation.
            device.off()
            log.info("valve CLOSED (BCM %d)", pin)

    return opener


async def _mock_valve_opener(seconds: float) -> None:
    """No-op valve: just wait for the requested duration."""
    log.info("valve OPEN for %.0f seconds (mock)", seconds)
    await asyncio.sleep(seconds)
    log.info("valve CLOSED (mock)")

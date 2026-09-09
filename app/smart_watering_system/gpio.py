"""GPIO / valve hardware abstraction.

On a Raspberry Pi this uses ``gpiozero.OutputDevice`` to drive a relay
or solenoid on a configurable BCM pin.  On any other platform (dev
machines, the simulator, non-Pi servers) it falls back to a mock that
just records the on/off calls — no hardware touched, but the timing
and event logging behave identically so the rest of the system can't
tell the difference.

Raspberry Pi setup
------------------
    pip install -r requirements.txt
    cp .env.example .env   # then edit pin / active-high as needed

Configuration is loaded from ``app/.env`` (or the shell environment)
by ``config.py`` — see ``.env.example`` for available keys.

Usage (from ``main.py``)::

    hardware = make_valve_hardware()
    await hardware.on()    # open the valve
    ...
    await hardware.off()   # close the valve

The hardware is stateless beyond the physical pin: it does *not* record
watering events or track open/close state.  That is the
``ValveController``'s job — it owns the event log and the
``valve_open`` flag, and calls into this hardware abstraction to drive
the actual pin.
"""
from __future__ import annotations

import asyncio
import logging

import config

log = logging.getLogger(__name__)


class ValveHardware:
    """Abstract valve hardware: async ``on()`` / ``off()``."""

    async def on(self) -> None:
        raise NotImplementedError

    async def off(self) -> None:
        raise NotImplementedError


def make_valve_hardware() -> ValveHardware:
    """Return a ``ValveHardware`` for the current platform.

    On a real Raspberry Pi (detected via ``/proc/device-tree/compatible``)
    this constructs a ``gpiozero.OutputDevice`` once and wraps it.  On
    every other platform it returns a mock that just logs — no GPIO,
    but the event log driven by the controller is identical.
    """
    if _is_raspberry_pi():
        return _make_pi_hardware()
    log.warning("not running on a Raspberry Pi — using mock valve hardware")
    return _MockValveHardware()


def _is_raspberry_pi() -> bool:
    try:
        with open("/proc/device-tree/compatible", "r") as f:
            return "raspberrypi" in f.read()
    except OSError:
        return False


class _MockValveHardware(ValveHardware):
    async def on(self) -> None:
        log.info("valve OPEN (mock)")

    async def off(self) -> None:
        log.info("valve CLOSED (mock)")


class _PiValveHardware(ValveHardware):
    """Drives a single ``gpiozero.OutputDevice`` for the valve."""

    def __init__(self, device) -> None:
        self._device = device

    async def on(self) -> None:
        # gpiozero pin writes are synchronous and very fast; run them in
        # a thread to keep the event loop responsive in case the library
        # ever blocks (it shouldn't, but this is cheap insurance).
        await asyncio.to_thread(self._device.on)

    async def off(self) -> None:
        await asyncio.to_thread(self._device.off)


def _make_pi_hardware() -> ValveHardware:
    """Build hardware around a single ``gpiozero.OutputDevice``."""
    import gpiozero

    pin = config.VALVE_GPIO_PIN
    active_high = config.VALVE_ACTIVE_HIGH
    device = gpiozero.OutputDevice(pin, active_high=active_high)
    log.info(
        "GPIO valve hardware initialized on BCM pin %d (active_high=%s)",
        pin,
        active_high,
    )
    return _PiValveHardware(device)

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from frontend.router import frontend_router
from smart_watering_system.gpio import make_valve_opener
from smart_watering_system.valve_controller import ValveController
from v1.router import v1_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the valve controller as a background task when the server
    # boots.  It ticks every hour, calling the watering engine and
    # driving the valve (currently a mock) until the server shuts down.
    controller = ValveController(valve_opener=make_valve_opener())
    task = asyncio.create_task(controller.run())
    log.info("valve controller started")
    try:
        yield
    finally:
        # Cancel the controller on shutdown so the process can exit
        # cleanly.  If the valve is currently open, the cancel will
        # interrupt `_open_valve`, the `finally` block there records
        # a close event, and `_recover_open_valve` on the next startup
        # will clean up any dangling state.
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("valve controller stopped")


app = FastAPI(lifespan=lifespan)
app.include_router(frontend_router)
app.include_router(v1_router)

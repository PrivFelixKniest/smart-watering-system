import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from frontend.router import frontend_router
from smart_watering_system.valve_controller import ValveController, make_default_controller
from v1.router import v1_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the valve controller as a background task when the server
    # boots.  It ticks every hour, calling the watering engine and
    # driving the valve (real GPIO on a Pi, mock elsewhere) until the
    # server shuts down.  The controller is also exposed on
    # ``app.state`` so the manual-control API endpoints can drive the
    # same valve instance the engine uses.
    controller = make_default_controller()
    app.state.valve_controller = controller
    task = asyncio.create_task(controller.run())
    log.info("valve controller started")
    try:
        yield
    finally:
        # Cancel the controller on shutdown so the process can exit
        # cleanly.  If the valve is currently open, the cancel will
        # interrupt the open-cycle, run()'s finally forces the hardware
        # off, and _recover_open_valve on the next startup cleans up any
        # dangling event-log state.
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("valve controller stopped")


app = FastAPI(lifespan=lifespan)
app.include_router(frontend_router)
app.include_router(v1_router)

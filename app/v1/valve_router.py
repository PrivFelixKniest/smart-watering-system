from typing import Annotated, Union

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header
from starlette.responses import HTMLResponse, JSONResponse

from frontend.templates import templates
from smart_watering_system.valve_controller import ValveController

valve_router = APIRouter(prefix="/valve")


def _controller(request: Request) -> ValveController:
    """The single shared valve controller owned by the app lifespan."""
    return request.app.state.valve_controller


def _body(controller: ValveController) -> dict:
    return {"valve_open": controller.is_open}


@valve_router.get("/state", response_class=HTMLResponse)
async def get_state(request: Request,
                   hx_request: Annotated[Union[str, None], Header()] = None):
    controller = _controller(request)
    body = _body(controller)

    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="components/home/valve-control.html",
            context=body,
        )
    return JSONResponse(content=jsonable_encoder(body))


@valve_router.post("/open", response_class=HTMLResponse)
async def post_open(request: Request,
                    hx_request: Annotated[Union[str, None], Header()] = None):
    controller = _controller(request)
    await controller.open_valve()
    body = _body(controller)

    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="components/home/valve-control.html",
            context=body,
            headers={"HX-Trigger": "valveStateChanged"},
        )
    return JSONResponse(content=jsonable_encoder(body))


@valve_router.post("/close", response_class=HTMLResponse)
async def post_close(request: Request,
                     hx_request: Annotated[Union[str, None], Header()] = None):
    controller = _controller(request)
    await controller.close_valve()
    body = _body(controller)

    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="components/home/valve-control.html",
            context=body,
            headers={"HX-Trigger": "valveStateChanged"},
        )
    return JSONResponse(content=jsonable_encoder(body))


@valve_router.post("/toggle", response_class=HTMLResponse)
async def post_toggle(request: Request,
                      hx_request: Annotated[Union[str, None], Header()] = None):
    """Toggle the valve: open if closed, close if open."""
    controller = _controller(request)
    if controller.is_open:
        await controller.close_valve()
    else:
        await controller.open_valve()
    body = _body(controller)

    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="components/home/valve-control.html",
            context=body,
            headers={"HX-Trigger": "valveStateChanged"},
        )
    return JSONResponse(content=jsonable_encoder(body))

from datetime import datetime
from typing import Union, Optional

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header, Form
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from typing_extensions import Annotated

from database.models import engine
from frontend.templates import templates
from service import water_consumption_service, forecast_service

water_consumption_router = APIRouter(prefix="/water-consumption")


@water_consumption_router.get("/usage", response_class=HTMLResponse)
async def get_usage(request: Request, start_date: Optional[datetime] = None,
                    hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        usage_per_day_in_seconds = await water_consumption_service.get_usage(db, start_date)

    usage_list = []
    for dayKey, usage in usage_per_day_in_seconds.items():
        usage_list.append({
            "day": dayKey.strftime("%d.%m"),
            "weekday": dayKey.strftime("%a"),
            "usage_in_seconds": usage
        })

    body = {
        "daily_usage": usage_list,
        "last_n_days": len(usage_list)
    }

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/water-consumption/daily-usage.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))


@water_consumption_router.get("/watering-demand", response_class=HTMLResponse)
async def get_sensitivity(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        demand = await water_consumption_service.get_watering_demand(db)

    body = {
        "watering_demand": demand
    }

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/water-consumption/watering-demand.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))


@water_consumption_router.put("/watering-demand", response_class=JSONResponse)
async def put_sensitivity(watering_demand: Annotated[int, Form()]):
    with Session(engine) as db:
        demand = await water_consumption_service.put_watering_demand(db, watering_demand)

    # Notify listeners (the forecast section) that demand changed so they
    # re-fetch with the new value.
    return JSONResponse(
        content=jsonable_encoder({"watering_demand": demand}),
        headers={"HX-Trigger": "wateringDemandChanged"},
    )


@water_consumption_router.get("/forecast", response_class=HTMLResponse)
async def get_forecast(request: Request, days: int = 7,
                       hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        city, day_results = await forecast_service.get_forecast_plan(db, days=days)

    total_minutes = sum(d["water_minutes"] for d in day_results)
    body = {
        "city": city,
        "days": day_results,
        "total_minutes": total_minutes,
        "watering_days": sum(1 for d in day_results if d["water_minutes"] > 0),
    }

    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="components/water-consumption/forecast.html",
            context=body,
        )
    return JSONResponse(content=jsonable_encoder(body))

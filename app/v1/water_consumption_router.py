from datetime import datetime
from typing import Union, Optional

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from typing_extensions import Annotated

from database.models import engine
from frontend.templates import templates
from service import water_consumption_service

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

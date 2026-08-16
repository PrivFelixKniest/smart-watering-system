from typing import Annotated, Union

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from database.models import engine
from frontend.templates import templates
from service import home_service

home_router = APIRouter(prefix="/home")


@home_router.get("/summary-cards", response_class=HTMLResponse)
async def get_summary_cards(request: Request,
                            hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        profile, recent_days = await home_service.get_home_cards(db, history_days=3)

    body = {
        "profile": {
            "name": profile.name,
            "city": profile.city,
            "watering_demand": profile.watering_demand,
        },
        "recent_days": recent_days,
    }

    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="components/home/summary-cards.html",
            context=body,
        )
    return JSONResponse(content=jsonable_encoder(body))

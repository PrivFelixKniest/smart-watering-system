from typing import Annotated, Union

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header
from service.shared import selected_profile_service
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import JSONResponse

from database.models import engine
from frontend.templates import templates

selected_profile_router = APIRouter(prefix="/selected-profile")


@selected_profile_router.get("/")
async def get_profiles(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        profile = await selected_profile_service.get_selected_profile(db)

    body = {
        "name": profile.name,
        "city": profile.city
    }

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/profiles/selected-profile-badge.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))

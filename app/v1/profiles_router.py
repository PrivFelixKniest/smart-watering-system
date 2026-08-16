from typing import Annotated, Union
from uuid import UUID

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header, Form
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from database.models import engine, Profile
from clients.geocoding_open_meteo import geocoding_open_meteo_api
from frontend.templates import templates
from service import profiles_service

profiles_router = APIRouter(prefix="/profiles")


async def get_profiles_body(db: Session, profiles: list[Profile]):
    rows = []
    for profile in profiles:
        lat, lon = None, None
        try:
            geocodes = await geocoding_open_meteo_api.search(profile.city)
            if geocodes.results:
                lat = geocodes.results[0].latitude
                lon = geocodes.results[0].longitude
        except Exception:
            pass
        rows.append({
            "selected": profile.selected_at is not None,
            "name": profile.name,
            "city": profile.city,
            "latitude": lat,
            "longitude": lon,
            "created_at": profile.created_at.strftime("%A, %H:%M"),
            "id": profile.id,
        })
    return {"profiles": rows}


@profiles_router.get("/", response_class=HTMLResponse)
async def get_profiles(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        profiles = await profiles_service.get_all_profiles(db)
        body = await get_profiles_body(db, profiles)

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/profiles/profiles-table.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))


@profiles_router.put("/", response_class=HTMLResponse)
async def put_profile(request: Request, name: Annotated[str, Form()],
                      city: Annotated[str, Form()], id: Annotated[str, Form()] = "",
                      hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        profiles = await profiles_service.upsert_profile(db, id, name, city)
        body = await get_profiles_body(db, profiles)

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/profiles/profiles-table.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))


@profiles_router.put("/{id}/select", response_class=HTMLResponse)
async def get_profiles(request: Request, id: UUID, hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        profiles = await profiles_service.select_profile(db, id)
        body = await get_profiles_body(db, profiles)

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/profiles/profiles-table.html",
                                          context=body, headers={"HX-Trigger": "profileSelected"})
    return JSONResponse(content=jsonable_encoder(body))


@profiles_router.delete("/{id}", response_class=HTMLResponse)
async def get_profiles(request: Request, id: UUID, hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        profiles = await profiles_service.delete_profile(db, id)
        body = await get_profiles_body(db, profiles)

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/profiles/profiles-table.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))

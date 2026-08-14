from fastapi.routing import APIRouter, Request
from starlette.staticfiles import StaticFiles

from frontend.templates import templates

frontend_router = APIRouter()

frontend_router.mount("/static", StaticFiles(directory="frontend/static", ), name="static")


@frontend_router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@frontend_router.get("/water-consumption")
async def water_consumption(request: Request):
    return templates.TemplateResponse(request=request, name="water-consumption.html")


@frontend_router.get("/profiles")
async def profiles(request: Request):
    return templates.TemplateResponse(request=request, name="profiles.html")

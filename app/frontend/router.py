from fastapi.routing import APIRouter, Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

frontendRouter = APIRouter()

frontendRouter.mount("/static", StaticFiles(directory="frontend/static", ), name="static")

templates = Jinja2Templates(directory="frontend/templates")


@frontendRouter.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@frontendRouter.get("/water-consumption")
async def waterConsumption(request: Request):
    return templates.TemplateResponse(request=request, name="water-consumption.html")


@frontendRouter.get("/settings")
async def settings(request: Request):
    return templates.TemplateResponse(request=request, name="settings.html")

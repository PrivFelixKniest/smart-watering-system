from fastapi.routing import APIRouter, Request
from starlette.templating import Jinja2Templates

frontendRouter = APIRouter()
templates = Jinja2Templates(directory="templates")

@frontendRouter.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

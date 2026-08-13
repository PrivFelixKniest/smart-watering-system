from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

homeRouter = APIRouter(prefix="/home")
templates = Jinja2Templates(directory="templates")

@homeRouter.get("/", response_class=HTMLResponse)
async def home(request: Request):
    pass

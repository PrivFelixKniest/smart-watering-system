from fastapi import APIRouter

from v1.home.router import homeRouter

v1Router = APIRouter(prefix="/v1")

v1Router.include_router(homeRouter)
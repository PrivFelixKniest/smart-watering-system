from fastapi import APIRouter

from v1.weather_router import weather_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(weather_router)

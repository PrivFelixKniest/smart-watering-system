from fastapi import APIRouter
from v1.profiles_router import profiles_router
from v1.selected_profile_router import selected_profile_router

from v1.weather_router import weather_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(weather_router)
v1_router.include_router(profiles_router)
v1_router.include_router(selected_profile_router)

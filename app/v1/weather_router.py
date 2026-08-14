from typing import Annotated, Union

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.params import Header
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from database.models import engine
from frontend.templates import templates
from service import weather_service

weather_router = APIRouter(prefix="/weather")


@weather_router.get("/", response_class=HTMLResponse)
async def get_weather(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    with Session(engine) as db:
        weather, city = await weather_service.get_weather(db)

    hourly_forecast = []

    for idx, time in enumerate(weather.hourly.time):
        hourly_forecast.append({
            "time": time.strftime("%A, %H:%M"),
            "temperature": weather.hourly.temperature_2m[idx],
            "precipitation": weather.hourly.precipitation[idx],
            "precipitation_probability": weather.hourly.precipitation_probability[idx],
            "et0": weather.hourly.et0_fao_evapotranspiration[idx],
        })

    if weather.current.precipitation >= 1.0:
        weather_image = "rainy"
    elif weather.current.precipitation > 0.0:
        weather_image = "cloudy"
    else:
        weather_image = "sunny"

    body = {
        "city": city,
        "current": {
            "temperature": weather.current.temperature_2m,
            "temperature_unit": weather.current_units.temperature_2m,
            "precipitation": weather.current.precipitation,
            "precipitation_unit": weather.current_units.precipitation,
            "wind_speed": weather.current.wind_speed_10m,
            "wind_speed_unit": weather.current_units.wind_speed_10m,
            "image_url": f"/static/{weather_image}.png",
        },
        "hourly_forecast": hourly_forecast,
        "hourly_units": {
            "temperature_unit": weather.hourly_units.temperature_2m,
            "precipitation_unit": weather.hourly_units.precipitation,
            "precipitation_probability_unit": weather.hourly_units.precipitation_probability,
            "et0_unit": weather.hourly_units.et0_fao_evapotranspiration,
        }
    }

    if hx_request:
        return templates.TemplateResponse(request=request, name="components/weather/weather.html",
                                          context=body)
    return JSONResponse(content=jsonable_encoder(body))

import httpx
from .models import WeatherResponse

OPEN_METEO_URL = "https://api.open-meteo.com"


async def get_forecast(lat: float, lon: float, forecast_days: int = 3) -> WeatherResponse:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,wind_speed_10m",
        "hourly": "temperature_2m,precipitation,precipitation_probability,et0_fao_evapotranspiration,soil_temperature_0cm,soil_moisture_1_to_3cm,snow_depth",
        "forecast_days": forecast_days,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(OPEN_METEO_URL + "/v1/forecast", params=params)
        r.raise_for_status()
        return WeatherResponse.model_validate(r.json())

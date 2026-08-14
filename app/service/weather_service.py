from sqlalchemy.orm import Session

from clients.geocoding_open_meteo import geocoding_open_meteo_api
from clients.open_meteo import open_meteo_api
from service.profile_service import get_selected_profile


async def get_weather(db: Session):
    profile = await get_selected_profile(db)

    geocodes = await geocoding_open_meteo_api.search(profile.city)

    geocode = geocodes.results[0]
    weather = await open_meteo_api.get_forecast(geocode.latitude, geocode.longitude)
    return weather, profile.city

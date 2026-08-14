import httpx

from clients.geocoding_open_meteo.models import GeocodingResponse

GEOCODING_OPEN_METEO_URL = "https://geocoding-api.open-meteo.com"


async def search(city_name: str) -> GeocodingResponse:
    params = {
        "name": city_name,
        "count": 1,
        "language": "en",
        "format": "json"
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(GEOCODING_OPEN_METEO_URL + "/v1/search", params=params)
        r.raise_for_status()
        return GeocodingResponse.model_validate(r.json())

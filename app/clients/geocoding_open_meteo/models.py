from pydantic import BaseModel


class GeocodingResult(BaseModel):
    name: str
    latitude: float
    longitude: float
    country: str


class GeocodingResponse(BaseModel):
    results: list[GeocodingResult]

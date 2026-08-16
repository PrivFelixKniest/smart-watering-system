from datetime import datetime

from pydantic import BaseModel


class CurrentUnits(BaseModel):
    temperature_2m: str
    precipitation: str
    wind_speed_10m: str


class CurrentWeather(BaseModel):
    temperature_2m: float
    precipitation: float
    wind_speed_10m: float


class HourlyUnits(BaseModel):
    time: str
    temperature_2m: str
    precipitation: str
    precipitation_probability: str
    et0_fao_evapotranspiration: str
    soil_temperature_0cm: str
    soil_moisture_1_to_3cm: str
    snow_depth: str


class HourlyForecast(BaseModel):
    time: list[datetime]
    temperature_2m: list[float]
    precipitation: list[float]
    precipitation_probability: list[float]
    et0_fao_evapotranspiration: list[float]
    soil_temperature_0cm: list[float]
    soil_moisture_1_to_3cm: list[float]
    snow_depth: list[float]


class WeatherResponse(BaseModel):
    latitude: float
    longitude: float
    elevation: float
    current_units: CurrentUnits
    current: CurrentWeather
    hourly_units: HourlyUnits
    hourly: HourlyForecast
    timezone: str = "UTC"

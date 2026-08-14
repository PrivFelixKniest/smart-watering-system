from datetime import datetime
from typing import Optional

from sqlalchemy import Uuid, String, create_engine, DateTime, Boolean, Float
from sqlalchemy.orm import declarative_base, mapped_column, Mapped

Base = declarative_base()


class TableBase():
    created_at = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at = mapped_column(DateTime, default=datetime.now, nullable=False, onupdate=datetime.now)


class Profile(Base, TableBase):
    __tablename__ = "profile"

    id = mapped_column(Uuid, primary_key=True)
    name = mapped_column(String, nullable=False)
    city = mapped_column(String, nullable=False)
    selected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    watering_demand: Mapped[Float] = mapped_column(Float, nullable=False, default=0.0)


class WaterTickEvent(Base, TableBase):
    __tablename__ = "water_tick_event"

    id = mapped_column(Uuid, primary_key=True)
    valve_open = mapped_column(Boolean, nullable=False)


engine = create_engine("sqlite:///app.db")

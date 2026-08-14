from datetime import datetime, timedelta, date
from typing import Optional, Dict

from sqlalchemy.orm import Session

from database.models import WaterTickEvent
from service.shared.selected_profile_service import get_selected_profile


def calculate_usage_time(event_list: list[WaterTickEvent]):
    total_time_open = timedelta(seconds=0)
    for idx, event in enumerate(event_list):
        if idx == len(event_list) - 1:
            continue

        if event.valve_open:
            total_time_open += event_list[idx + 1].created_at - event.created_at

    return total_time_open


async def get_usage(db: Session, start_date: Optional[datetime]):
    if start_date is None:
        start_date = date.today() - timedelta(days=13)

    events = db.query(WaterTickEvent).where(WaterTickEvent.created_at >= start_date).order_by(
        WaterTickEvent.created_at.asc()).all()

    events_per_day: Dict[date, list[WaterTickEvent]] = {}

    for event in events:
        event_day_key = event.created_at.date()
        if events_per_day.get(event_day_key, None) is None:
            events_per_day[event_day_key] = [event]
        else:
            events_per_day[event_day_key].append(event)

    usage_per_day_in_seconds: Dict[date, float] = {}

    for dayKey, event_list in events_per_day.items():
        open_time = calculate_usage_time(event_list)
        usage_per_day_in_seconds[dayKey] = open_time.total_seconds()

    return usage_per_day_in_seconds


async def get_watering_demand(db: Session):
    profile = await get_selected_profile(db)
    return profile.watering_demand


async def put_watering_demand(db: Session, watering_demand: int):
    profile = await get_selected_profile(db)
    profile.watering_demand = watering_demand
    db.commit()
    return profile.watering_demand

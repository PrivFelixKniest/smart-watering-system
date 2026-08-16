"""Data for the two summary cards on the home page: recent watering history
+ current demand, and the currently selected profile.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from service.shared.selected_profile_service import get_selected_profile
from service.water_consumption_service import get_usage


async def get_home_cards(db: Session, history_days: int = 3):
    """Return (profile, demand, recent_days) where recent_days is a list of
    {day, weekday, minutes} for the last `history_days` days (oldest first).
    """
    profile = await get_selected_profile(db)
    start_date = date.today() - timedelta(days=history_days - 1)
    usage_per_day = await get_usage(db, start_date)

    # Build a dense list covering every day in the window (missing days = 0).
    recent_days = []
    for i in range(history_days):
        d = start_date + timedelta(days=i)
        seconds = usage_per_day.get(d, 0.0)
        recent_days.append({
            "day": d.strftime("%d.%m"),
            "weekday": d.strftime("%a"),
            "minutes": int(round(seconds / 60.0)),
            "seconds": seconds,
        })

    return profile, recent_days

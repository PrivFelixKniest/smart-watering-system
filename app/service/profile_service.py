from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import Profile


async def get_selected_profile(db: Session):
    profile = db.execute(select(Profile).order_by(Profile.selected_at.desc())).scalar()
    return profile

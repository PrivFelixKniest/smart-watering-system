from sqlalchemy.orm import Session

from database.models import Profile


async def get_selected_profile(db: Session):
    profile = db.query(Profile).where(Profile.selected_at.is_not(None)).first()
    if profile is None:
        raise RuntimeError(
            "Selected Profile is not allowed to be null at runtime, there always needs to be one selected profile.")
    return profile

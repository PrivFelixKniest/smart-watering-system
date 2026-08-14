import uuid
from datetime import datetime
from uuid import UUID

from clients.geocoding_open_meteo import geocoding_open_meteo_api
from service.shared.selected_profile_service import get_selected_profile
from sqlalchemy.orm import Session

from database.models import Profile


async def get_all_profiles(db: Session):
    profiles = db.query(Profile).order_by(Profile.created_at.asc()).all()
    return profiles


async def upsert_profile(db: Session, id: str, name: str, city: str):
    georesponse = await geocoding_open_meteo_api.search(city)

    if len(georesponse.results) == 0:
        raise RuntimeError("City was not found")

    if id == "":
        db.add(Profile(id=uuid.uuid4(), name=name, city=city))
    else:
        profile = db.query(Profile).where(Profile.id == UUID(id)).first()
        if profile is None:
            raise RuntimeError("Profile with this ID does not exist")
        profile.city = city
        profile.name = name
    db.commit()
    return await get_all_profiles(db)


async def select_profile(db: Session, id: UUID):
    selected_profile = await get_selected_profile(db)
    new_selected_profile = db.query(Profile).where(Profile.id == id).first()
    if new_selected_profile is None:
        raise RuntimeError("Profile with this ID does not exist")

    selected_profile.selected_at = None
    new_selected_profile.selected_at = datetime.now()
    db.commit()
    return await get_all_profiles(db)


async def delete_profile(db: Session, id: UUID):
    profile = db.query(Profile).where(Profile.id == id).first()
    if profile is None:
        raise RuntimeError("Profile with this ID does not exist")

    if profile.selected_at is not None:
        raise RuntimeError("Can not delete selecte profile")

    db.delete(profile)
    db.commit()

    return await get_all_profiles(db)

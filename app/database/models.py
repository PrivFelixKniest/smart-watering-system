from sqlalchemy import Column, Uuid, String, create_engine, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Profile(Base):
    __tablename__ = "profile"

    id = Column(Uuid, primary_key=True)
    name = Column(String)
    city = Column(String)
    selected_at = Column(DateTime, nullable=True)


engine = create_engine("sqlite:///app.db")

Base.metadata.create_all(engine)

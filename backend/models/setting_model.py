# backend/models/setting_model.py

from sqlalchemy import Column, String, TEXT
from backend.models.base_model import Base

class GlobalSettings(Base):
    __tablename__ = "GlobalSettings"

    key = Column(String(50), primary_key=True)
    value = Column(TEXT, nullable=True)


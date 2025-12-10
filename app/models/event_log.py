from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from app.core.database import Base

class EventLog(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    
    # Data Identitas
    device = Column(String, index=True)
    auth_id = Column(String, index=True)
    date = Column(String) 
    temperature = Column(Float, nullable=True)
    
    # Data Gambar
    picture_path = Column(String, nullable=True)
    
    # Metadata
    source = Column(String)     
    created_at = Column(DateTime(timezone=True), server_default=func.now())
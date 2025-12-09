from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    
    name = Column(String, index=True)
    ip_address = Column(String, unique=True, index=True)
    port = Column(Integer, default=8000)
    username = Column(String)
    password = Column(String)
    
    # --- TAMBAHAN BARU ---
    target_api = Column(String, nullable=True) 
    # ---------------------

    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
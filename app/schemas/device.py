from pydantic import BaseModel, IPvAnyAddress
from typing import Optional, List
from datetime import datetime

# Base Schema (Shared properties)
class DeviceBase(BaseModel):
    name: str
    ip_address: str
    port: int = 8000
    username: str
    password: str
    is_active: bool = True

# Schema untuk Create (POST)
class DeviceCreate(DeviceBase):
    pass

# Schema untuk Update (PUT)
class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

# Schema untuk Response (GET) - Menyembunyikan Password
class DeviceResponse(DeviceBase):
    id: int
    last_seen: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True # Dulu orm_mode = True
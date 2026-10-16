import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    display_name: str | None
    photo_url: str | None
    created_at: datetime


class DeviceRegister(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    user_agent: str | None = Field(default=None, max_length=500)


class DeviceUnregister(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


class TestPushResult(BaseModel):
    channel: str
    devices: int
    delivered: int
    error: str | None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID | None
    channel: str
    title: str
    body: str
    status: str
    error: str | None
    created_at: datetime
    sent_at: datetime | None

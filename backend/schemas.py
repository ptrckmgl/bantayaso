from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()


ReviewStatus = Literal["pending", "reviewed", "flagged"]


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    barangay: str
    latitude: float
    longitude: float
    description: str


class LocationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    barangay: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)


class DeviceCreate(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,64}$")
    name: str = Field(min_length=2, max_length=120)
    location_id: int | None = None
    new_location: LocationCreate | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: str
    last_seen: datetime | None
    location: LocationOut

    @field_serializer("last_seen")
    def serialize_last_seen(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class DetectionCreate(BaseModel):
    device_id: str
    timestamp: datetime
    dog_count: int = Field(ge=0, le=100)
    person_count: int = Field(default=0, ge=0, le=100)
    unaccompanied: bool | None = None
    track_id: int | None = Field(default=None, ge=0)
    duration_s: float | None = Field(default=None, ge=0)
    accompanied_ratio: float | None = Field(default=None, ge=0, le=1)
    max_dogs_in_view: int | None = Field(default=None, ge=0)
    snapshot_dog_count: int | None = Field(default=None, ge=0)
    event_key: str | None = Field(default=None, min_length=1, max_length=120)
    event_state: Literal["active", "closed"] = "closed"
    event_sequence: int = Field(default=0, ge=0)
    confidence: float = Field(ge=0, le=1)
    review_status: ReviewStatus = "pending"
    source: Literal["simulator", "camera"] = "simulator"


class DetectionPatch(BaseModel):
    review_status: ReviewStatus


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    device_id: str
    timestamp: datetime
    dog_count: int
    person_count: int
    unaccompanied: bool | None
    track_id: int | None
    duration_s: float | None
    accompanied_ratio: float | None
    max_dogs_in_view: int | None
    snapshot_dog_count: int | None
    event_state: str
    event_sequence: int
    confidence: float
    review_status: ReviewStatus
    snapshot_path: str | None
    source: str
    location: LocationOut
    device: DeviceOut

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return utc_iso(value) or ""

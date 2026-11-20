from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    barangay: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    devices: Mapped[list["Device"]] = relationship(back_populates="location")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[str] = mapped_column(String(20), default="offline")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    location: Mapped[Location] = relationship(back_populates="devices")
    detections: Mapped[list["Detection"]] = relationship(back_populates="device")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    dog_count: Mapped[int] = mapped_column(Integer)
    person_count: Mapped[int] = mapped_column(Integer, default=0)
    unaccompanied: Mapped[bool | None] = mapped_column(nullable=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    accompanied_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_dogs_in_view: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Most dogs seen together for a sustained time (the detector's --together-hold); decides packs.
    dogs_together: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_dog_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    event_state: Mapped[str] = mapped_column(String(20), default="closed")
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    snapshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="simulator")
    device: Mapped[Device] = relationship(back_populates="detections")
    location: Mapped[Location] = relationship()

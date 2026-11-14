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
    confidence: Mapped[float] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    snapshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="simulator")
    device: Mapped[Device] = relationship(back_populates="detections")
    location: Mapped[Location] = relationship()

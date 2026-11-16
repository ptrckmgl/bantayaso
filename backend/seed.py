"""One example camera and location, with no preloaded detections."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Device, Location


def seed_database(db: Session):
    """Give the simulator a usable camera while leaving the dashboard empty."""
    if db.scalar(select(Location.id).limit(1)) is not None:
        return

    location = Location(
        name="Town Plaza",
        barangay="Poblacion",
        latitude=14.1956,
        longitude=120.8765,
        description="Example monitoring location for the prototype",
    )
    db.add(location)
    db.flush()
    db.add(Device(id="CAM-001", name="Example Plaza Camera", location_id=location.id, status="offline"))
    db.commit()

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .database import BASE_DIR
from .models import Detection, Device, Location
from .schemas import DetectionCreate

SNAPSHOT_DIR = BASE_DIR / "storage" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
MANILA = timezone(timedelta(hours=8))


class ReviewRequiredError(Exception):
    """A detection must be reviewed before it can be deleted."""


def local_date(value: datetime):
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(MANILA).date()


def detection_query():
    return select(Detection).options(
        joinedload(Detection.device).joinedload(Device.location), joinedload(Detection.location)
    )


def create_detection(db: Session, payload: DetectionCreate, snapshot: bytes | None = None, suffix: str = ".png"):
    device = db.get(Device, payload.device_id)
    if device is None:
        raise ValueError("Device not found")
    detection_id = f"DET-{uuid4().hex[:8].upper()}"
    snapshot_path = None
    if snapshot:
        filename = f"{detection_id}{suffix}"
        (SNAPSHOT_DIR / filename).write_bytes(snapshot)
        snapshot_path = f"/snapshots/{filename}"
    timestamp = payload.timestamp.replace(tzinfo=timezone.utc) if payload.timestamp.tzinfo is None else payload.timestamp.astimezone(timezone.utc)
    event = Detection(
        id=detection_id,
        device_id=device.id,
        location_id=device.location_id,
        timestamp=timestamp,
        dog_count=payload.dog_count,
        confidence=payload.confidence,
        review_status=payload.review_status,
        snapshot_path=snapshot_path,
        source=payload.source,
    )
    # A simulated upload demonstrates ingestion, but does not prove a camera is connected.
    if payload.source == "camera":
        device.status = "online"
        device.last_seen = timestamp
    db.add(event)
    db.commit()
    return db.execute(detection_query().where(Detection.id == detection_id)).scalar_one()


def _remove_unreferenced_snapshot(db: Session, snapshot_path: str | None):
    if not snapshot_path or not snapshot_path.startswith("/snapshots/"):
        return
    filename = snapshot_path.removeprefix("/snapshots/")
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        return
    if db.scalar(select(func.count(Detection.id)).where(Detection.snapshot_path == snapshot_path)):
        return
    (SNAPSHOT_DIR / filename).unlink(missing_ok=True)


def delete_detection(db: Session, detection_id: str):
    event = db.get(Detection, detection_id)
    if event is None:
        raise ValueError("Detection not found")
    if event.review_status != "reviewed":
        raise ReviewRequiredError("Mark this detection as Reviewed before deleting it")
    snapshot_path = event.snapshot_path
    db.delete(event)
    db.commit()
    _remove_unreferenced_snapshot(db, snapshot_path)
    return detection_id


def clear_detections(db: Session):
    events = db.execute(select(Detection)).scalars().all()
    if any(event.review_status != "reviewed" for event in events):
        raise ReviewRequiredError("Review every detection before using Clear all")
    snapshot_paths = {event.snapshot_path for event in events if event.snapshot_path}
    for event in events:
        db.delete(event)
    db.commit()
    for snapshot_path in snapshot_paths:
        _remove_unreferenced_snapshot(db, snapshot_path)
    return len(events)


def dashboard_summary(db: Session):
    today = datetime.now(MANILA).date()
    events = db.execute(select(Detection)).scalars().all()
    today_events = [event for event in events if local_date(event.timestamp) == today]
    devices = db.execute(select(Device)).scalars().all()
    return {
        "dogs_today": sum(event.dog_count for event in today_events),
        "detections_today": len(today_events),
        "total_detections": len(events),
        "active_cameras": sum(device.status == "online" for device in devices),
        "total_cameras": len(devices),
        "pending_reviews": sum(event.review_status == "pending" for event in events),
        "locations_monitored": db.scalar(select(func.count(Location.id))) or 0,
    }


def analytics(db: Session):
    events = db.execute(select(Detection).order_by(Detection.timestamp)).scalars().all()
    today = datetime.now(MANILA).date()
    daily = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        matches = [event for event in events if local_date(event.timestamp) == day]
        daily.append({"date": day.isoformat(), "detections": len(matches), "dogs": sum(e.dog_count for e in matches)})
    locations = db.execute(select(Location)).scalars().all()
    by_location = [
        {"location_id": loc.id, "name": loc.name, "count": sum(e.dog_count for e in events if e.location_id == loc.id)}
        for loc in locations
    ]
    return {"daily": daily, "by_location": by_location}

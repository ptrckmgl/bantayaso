from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .database import BASE_DIR
from .models import Detection, Device, Location
from .schemas import DetectionCreate

SNAPSHOT_DIR = BASE_DIR / "storage" / "snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
MANILA = timezone(timedelta(hours=8))
# A camera that has sent nothing (no heartbeat, no report) for this long is shown offline.
OFFLINE_AFTER = timedelta(seconds=int(os.getenv("CAMERA_OFFLINE_AFTER_S", "120")))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def refresh_device_status(db: Session) -> bool:
    """Mark online cameras offline once they have been silent for OFFLINE_AFTER. Returns True if any changed."""
    cutoff = datetime.now(timezone.utc) - OFFLINE_AFTER
    changed = False
    for device in db.execute(select(Device).where(Device.status == "online")).scalars():
        if device.last_seen is None or _aware(device.last_seen) < cutoff:
            device.status = "offline"
            changed = True
    if changed:
        db.commit()
    return changed


def device_heartbeat(db: Session, device_id: str, state: str) -> bool:
    """Record a camera heartbeat. A running camera is online; a stopped one is offline at once.
    Returns True if the camera's status changed."""
    device = db.get(Device, device_id)
    if device is None:
        raise ValueError("Device not found")
    before = device.status
    device.status = "offline" if state == "stopped" else "online"
    device.last_seen = datetime.now(timezone.utc)
    db.commit()
    return device.status != before


def local_date(value: datetime):
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(MANILA).date()


def detection_query():
    return select(Detection).options(
        joinedload(Detection.device).joinedload(Device.location), joinedload(Detection.location)
    )


def create_detection(db: Session, payload: DetectionCreate, snapshot: bytes | None = None, suffix: str = ".png"):
    timestamp = payload.timestamp.replace(tzinfo=timezone.utc) if payload.timestamp.tzinfo is None else payload.timestamp.astimezone(timezone.utc)
    # A camera report with dogs but no observed person cannot be accompanied.
    # Normalize older camera clients that may still send False for this case.
    unaccompanied = (True if payload.source == "camera" and payload.dog_count > 0
                     and payload.person_count == 0 else payload.unaccompanied)
    if payload.event_key:
        existing = db.execute(detection_query().where(Detection.event_key == payload.event_key)).scalar_one_or_none()
        if existing:
            if (existing.source == "camera" and payload.source == "camera"
                    and existing.device_id == payload.device_id
                    and payload.event_sequence > existing.event_sequence):
                existing.timestamp = timestamp
                existing.dog_count = payload.dog_count
                existing.person_count = payload.person_count
                existing.unaccompanied = unaccompanied
                existing.duration_s = payload.duration_s
                existing.accompanied_ratio = payload.accompanied_ratio
                existing.max_dogs_in_view = payload.max_dogs_in_view
                existing.dogs_together = payload.dogs_together
                existing.confidence = payload.confidence
                existing.event_state = payload.event_state
                existing.event_sequence = payload.event_sequence
                # Keep the operator review state. An update carries an image only when the camera
                # saw more dogs in one frame than the current image shows; it replaces the old one.
                old_snapshot = None
                if snapshot:
                    old_snapshot = existing.snapshot_path
                    filename = f"{existing.id}-{payload.event_sequence}{suffix}"
                    (SNAPSHOT_DIR / filename).write_bytes(snapshot)
                    existing.snapshot_path = f"/snapshots/{filename}"
                    existing.snapshot_dog_count = payload.snapshot_dog_count
                existing.device.status = "online"
                existing.device.last_seen = timestamp
                db.commit()
                if old_snapshot and old_snapshot != existing.snapshot_path:
                    _remove_unreferenced_snapshot(db, old_snapshot)
            return existing
    device = db.get(Device, payload.device_id)
    if device is None:
        raise ValueError("Device not found")
    detection_id = f"DET-{uuid4().hex[:8].upper()}"
    snapshot_path = None
    if snapshot:
        filename = f"{detection_id}{suffix}"
        (SNAPSHOT_DIR / filename).write_bytes(snapshot)
        snapshot_path = f"/snapshots/{filename}"
    event = Detection(
        id=detection_id,
        device_id=device.id,
        location_id=device.location_id,
        timestamp=timestamp,
        dog_count=payload.dog_count,
        person_count=payload.person_count,
        unaccompanied=unaccompanied,
        track_id=payload.track_id,
        duration_s=payload.duration_s,
        accompanied_ratio=payload.accompanied_ratio,
        max_dogs_in_view=payload.max_dogs_in_view,
        dogs_together=payload.dogs_together,
        snapshot_dog_count=payload.snapshot_dog_count,
        event_key=payload.event_key,
        event_state=payload.event_state,
        event_sequence=payload.event_sequence,
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
    snapshot_path = event.snapshot_path
    db.delete(event)
    db.commit()
    _remove_unreferenced_snapshot(db, snapshot_path)
    return detection_id


def clear_detections(db: Session):
    events = db.execute(select(Detection)).scalars().all()
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


def _local(value: datetime):
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(MANILA)


def hotspots(db: Session, window_hours: int = 24, threshold: int = 5, basis: str = "dogs", pack_size: int = 3):
    """Zones whose activity in the last `window_hours` reaches `threshold` (a fixed limit set by the operator).

    With basis "dogs", the limit counts dogs, summed from each report's peak count like the other
    dashboard totals, so it measures activity, not unique dogs. With basis "packs", it counts pack
    sightings: reports in which at least `pack_size` dogs were seen together. `crossed_at` is when the
    running total in the window reached the limit.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    events = db.execute(select(Detection).order_by(Detection.timestamp)).scalars().all()
    recent = [event for event in events if _local(event.timestamp) >= since and event.dog_count > 0]
    zones = []
    for location in db.execute(select(Location).order_by(Location.name)).scalars().all():
        matches = [event for event in recent if event.location_id == location.id]
        total, crossed_at = 0, None
        for event in matches:
            total += event.dog_count if basis == "dogs" else is_pack(event, pack_size)
            if crossed_at is None and total >= threshold:
                crossed_at = _local(event.timestamp)
        zones.append({
            "location_id": location.id, "name": location.name, "barangay": location.barangay,
            "count": total, "dogs": sum(e.dog_count for e in matches),
            "packs": sum(is_pack(e, pack_size) for e in matches), "reports": len(matches),
            "last_seen": _local(matches[-1].timestamp).isoformat() if matches else None,
            "is_hotspot": total >= threshold,
            "crossed_at": crossed_at.isoformat() if crossed_at else None,
        })
    zones.sort(key=lambda zone: (not zone["is_hotspot"], -zone["count"], -zone["dogs"], zone["name"]))
    return {"window_hours": window_hours, "threshold": threshold, "basis": basis, "pack_size": pack_size,
            "generated_at": _local(now).isoformat(), "zones": zones}


def _peak_hour(hours: list[dict]):
    best = max(hours, key=lambda item: item["dogs"])
    return best["hour"] if best["dogs"] > 0 else None


def group_size(event: Detection) -> int:
    """Dogs seen together in a report. Older reports and scenarios have no sustained count, so their
    peak count is used."""
    return event.dogs_together if event.dogs_together is not None else event.dog_count


def is_pack(event: Detection, pack_size: int) -> bool:
    return event.dog_count > 0 and group_size(event) >= pack_size


def activity_report(db: Session, start=None, end=None, pack_size: int = 3):
    """Dog activity between two local (Manila) dates, inclusive: per day, per hour of day, and per zone.
    A report is a pack when at least `pack_size` dogs were seen together."""
    today = datetime.now(MANILA).date()
    end = end or today
    start = start or end - timedelta(days=6)
    if start > end:
        start, end = end, start
    start = max(start, end - timedelta(days=365))
    events = [event for event in db.execute(select(Detection).order_by(Detection.timestamp)).scalars().all()
              if start <= _local(event.timestamp).date() <= end]

    def hourly(rows):
        result = [{"hour": hour, "dogs": 0, "detections": 0, "packs": 0} for hour in range(24)]
        for event in rows:
            slot = result[_local(event.timestamp).hour]
            slot["dogs"] += event.dog_count
            slot["detections"] += 1
            slot["packs"] += is_pack(event, pack_size)
        return result

    daily = []
    day = start
    while day <= end:
        matches = [event for event in events if _local(event.timestamp).date() == day]
        daily.append({"date": day.isoformat(), "detections": len(matches), "dogs": sum(e.dog_count for e in matches),
                      "packs": sum(is_pack(e, pack_size) for e in matches)})
        day += timedelta(days=1)
    hours = hourly(events)
    zones = []
    for location in db.execute(select(Location).order_by(Location.name)).scalars().all():
        matches = [event for event in events if event.location_id == location.id]
        zone_hours = hourly(matches)
        zones.append({"location_id": location.id, "name": location.name, "barangay": location.barangay,
                      "dogs": sum(e.dog_count for e in matches), "detections": len(matches),
                      "packs": sum(is_pack(e, pack_size) for e in matches),
                      "largest_group": max((group_size(e) for e in matches if e.dog_count > 0), default=0),
                      "night_dogs": sum(e.dog_count for e in matches if _local(e.timestamp).hour >= 18 or _local(e.timestamp).hour < 6),
                      "peak_hour": _peak_hour(zone_hours), "hourly": zone_hours})
    zones.sort(key=lambda zone: (-zone["dogs"], zone["name"]))
    return {"start": start.isoformat(), "end": end.isoformat(), "pack_size": pack_size,
            "packs": sum(is_pack(e, pack_size) for e in events), "dogs": sum(e.dog_count for e in events),
            "detections": len(events), "peak_hour": _peak_hour(hours), "daily": daily, "hourly": hours,
            "by_location": zones}

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .database import Base, SessionLocal, engine, get_db
from .models import Detection, Device, Location
from .schemas import DetectionCreate, DetectionOut, DetectionPatch, DeviceCreate, DeviceOut, LocationCreate, LocationOut
from .seed import seed_database
from .services import SNAPSHOT_DIR, ReviewRequiredError, analytics, clear_detections, create_detection, dashboard_summary, delete_detection, detection_query


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(title="StrayWatch Dashboard API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard/summary")
def summary(db: Session = Depends(get_db)):
    return dashboard_summary(db)


@app.get("/api/locations", response_model=list[LocationOut])
def locations(db: Session = Depends(get_db)):
    return db.execute(select(Location).order_by(Location.id)).scalars().all()


def ensure_location_name_available(db: Session, name: str):
    if db.scalar(select(Location.id).where(func.lower(Location.name) == name.lower())):
        raise HTTPException(409, "Monitoring zone name already exists")


def make_location(payload: LocationCreate):
    # Zero means coordinates have not been provided yet; the prototype map is schematic.
    return Location(name=payload.name, barangay=payload.barangay,
                    description=payload.description, latitude=0.0, longitude=0.0)


@app.post("/api/locations", response_model=LocationOut, status_code=201)
def add_location(payload: LocationCreate, db: Session = Depends(get_db)):
    ensure_location_name_available(db, payload.name)
    location = make_location(payload)
    db.add(location)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Monitoring zone name already exists") from error
    db.refresh(location)
    return location


@app.get("/api/devices", response_model=list[DeviceOut])
def devices(db: Session = Depends(get_db)):
    return db.execute(select(Device).options(joinedload(Device.location)).order_by(Device.id)).scalars().all()


@app.post("/api/devices", response_model=DeviceOut, status_code=201)
def add_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    if db.get(Device, payload.id):
        raise HTTPException(409, "Device ID already exists")
    if (payload.location_id is None) == (payload.new_location is None):
        raise HTTPException(422, "Choose an existing zone or provide one new zone")
    if payload.new_location:
        ensure_location_name_available(db, payload.new_location.name)
        location = make_location(payload.new_location)
        db.add(location)
    else:
        location = db.get(Location, payload.location_id)
        if not location:
            raise HTTPException(404, "Location not found")
    device = Device(id=payload.id, name=payload.name, location=location)
    db.add(device)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Camera ID or monitoring zone already exists") from error
    db.refresh(device)
    return device


@app.get("/api/devices/{device_id}", response_model=DeviceOut)
def device(device_id: str, db: Session = Depends(get_db)):
    result = db.get(Device, device_id)
    if not result:
        raise HTTPException(404, "Device not found")
    return result


@app.get("/api/detections", response_model=list[DetectionOut])
def detections(status: str | None = None, location_id: int | None = None, limit: int = Query(100, ge=1, le=500),
               db: Session = Depends(get_db)):
    query = detection_query().order_by(Detection.timestamp.desc()).limit(limit)
    if status and status != "all":
        query = query.where(Detection.review_status == status)
    if location_id:
        query = query.where(Detection.location_id == location_id)
    return db.execute(query).scalars().all()


@app.get("/api/detections/{detection_id}", response_model=DetectionOut)
def detection(detection_id: str, db: Session = Depends(get_db)):
    result = db.execute(detection_query().where(Detection.id == detection_id)).scalar_one_or_none()
    if not result:
        raise HTTPException(404, "Detection not found")
    return result


@app.post("/api/detections", response_model=DetectionOut, status_code=201)
async def add_detection(device_id: str = Form(...), timestamp: datetime = Form(...), dog_count: int = Form(...),
                        confidence: float = Form(...), source: str = Form("simulator"),
                        snapshot: UploadFile | None = File(None), db: Session = Depends(get_db)):
    try:
        payload = DetectionCreate(device_id=device_id, timestamp=timestamp, dog_count=dog_count,
                                  confidence=confidence, source=source)
    except Exception as error:
        raise HTTPException(422, str(error)) from error
    data, suffix = None, ".png"
    if snapshot:
        allowed = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        if snapshot.content_type not in allowed:
            raise HTTPException(415, "Snapshot must be PNG, JPEG, or WebP")
        data = await snapshot.read(5_000_001)
        if len(data) > 5_000_000:
            raise HTTPException(413, "Snapshot exceeds 5 MB")
        suffix = allowed[snapshot.content_type]
    try:
        return create_detection(db, payload, data, suffix)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.patch("/api/detections/{detection_id}", response_model=DetectionOut)
def update_detection(detection_id: str, payload: DetectionPatch, db: Session = Depends(get_db)):
    result = db.get(Detection, detection_id)
    if not result:
        raise HTTPException(404, "Detection not found")
    result.review_status = payload.review_status
    db.commit()
    return db.execute(detection_query().where(Detection.id == detection_id)).scalar_one()


@app.delete("/api/detections/{detection_id}")
def remove_detection(detection_id: str, db: Session = Depends(get_db)):
    try:
        return {"deleted_id": delete_detection(db, detection_id)}
    except ReviewRequiredError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.delete("/api/detections")
def remove_all_detections(db: Session = Depends(get_db)):
    try:
        return {"deleted": clear_detections(db)}
    except ReviewRequiredError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/analytics")
def analytics_endpoint(db: Session = Depends(get_db)):
    return analytics(db)


@app.post("/api/demo/simulate", response_model=DetectionOut, status_code=201)
def simulate_demo(device_id: str = "CAM-001", dog_count: int = Query(2, ge=1, le=4), db: Session = Depends(get_db)):
    """Dashboard demo control; the CLI simulator separately posts to /api/detections."""
    from iot.simulator import make_snapshot

    if not db.get(Device, device_id):
        raise HTTPException(404, "Device not found")
    payload = DetectionCreate(device_id=device_id, timestamp=datetime.now(timezone.utc),
                              dog_count=dog_count, confidence=.93, source="simulator")
    return create_detection(db, payload, make_snapshot(dog_count, device_id))

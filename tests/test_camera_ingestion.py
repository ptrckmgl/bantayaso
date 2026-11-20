"""Exercise the camera upload against a migrated prototype database."""

import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import text
from starlette.datastructures import Headers
from fastapi import UploadFile


class CameraIngestionTest(unittest.TestCase):
    def test_camera_event_with_snapshot_and_duplicate_key(self):
        with tempfile.TemporaryDirectory() as directory:
            os.environ["DATABASE_URL"] = f"sqlite:///{(Path(directory) / 'test.db').as_posix()}"
            from backend import main, services
            from backend.database import SessionLocal, engine
            from backend.models import Detection

            # An older dashboard database has no model-specific detection fields.
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE detections (
                    id VARCHAR(64) PRIMARY KEY, device_id VARCHAR(64), location_id INTEGER,
                    timestamp DATETIME, dog_count INTEGER, confidence FLOAT,
                    review_status VARCHAR(20), snapshot_path VARCHAR(255), source VARCHAR(20)
                )"""))

            async def run():
                async with main.lifespan(main.app):
                    original_dir = services.SNAPSHOT_DIR
                    services.SNAPSHOT_DIR = Path(directory) / "snapshots"
                    services.SNAPSHOT_DIR.mkdir()
                    try:
                        with SessionLocal() as db:
                            def upload():
                                return UploadFile(file=BytesIO(b"\xff\xd8test-jpeg"), filename="frame.jpg",
                                                  headers=Headers({"content-type": "image/jpeg"}))

                            args = dict(device_id="CAM-001", timestamp=datetime.now(timezone.utc),
                                        dog_count=1, confidence=.91, source="camera", person_count=2,
                                        unaccompanied=True, track_id=7, duration_s=4.5,
                                        accompanied_ratio=0.1, max_dogs_in_view=3, snapshot_dog_count=2, dogs_together=3,
                                        event_key="session-7", event_state="active", event_sequence=0,
                                        db=db)
                            first = await main.add_detection(snapshot=upload(), **args)
                            second = await main.add_detection(snapshot=upload(), **args)
                            self.assertEqual(first.id, second.id)
                            self.assertEqual(db.query(Detection).count(), 1)
                            self.assertEqual(first.location.name, "Town Plaza")
                            self.assertEqual(first.person_count, 2)
                            self.assertTrue(first.unaccompanied)
                            self.assertEqual(first.max_dogs_in_view, 3)
                            self.assertEqual(first.dogs_together, 3)
                            self.assertEqual(first.snapshot_dog_count, 2)
                            self.assertTrue((services.SNAPSHOT_DIR / first.snapshot_path.split("/")[-1]).exists())
                            first.review_status = "reviewed"
                            db.commit()
                            updated = await main.add_detection(
                                **{**args, "dog_count": 3, "person_count": 4,
                                   "event_sequence": 1, "event_state": "closed", "snapshot": None})
                            self.assertEqual(updated.id, first.id)
                            self.assertEqual(updated.dog_count, 3)
                            self.assertEqual(updated.person_count, 4)
                            self.assertEqual(updated.event_state, "closed")
                            self.assertEqual(updated.review_status, "reviewed")
                            self.assertEqual(updated.snapshot_dog_count, 2)
                            stale = await main.add_detection(snapshot=None, **args)
                            self.assertEqual(stale.dog_count, 3)
                            self.assertEqual(db.query(Detection).count(), 1)
                            person = await main.add_detection(
                                device_id="CAM-001", timestamp=datetime.now(timezone.utc), dog_count=0,
                                confidence=.82, source="camera", person_count=3, event_key="session-person-1",
                                unaccompanied=None, track_id=None, duration_s=None,
                                accompanied_ratio=None, max_dogs_in_view=None, snapshot_dog_count=0, dogs_together=None,
                                event_state="active", event_sequence=0,
                                snapshot=upload(), db=db)
                            self.assertEqual(person.dog_count, 0)
                            self.assertEqual(person.person_count, 3)
                            self.assertIsNone(person.unaccompanied)
                            no_person_args = {**args, "event_key": "session-no-person",
                                              "person_count": 0, "unaccompanied": False}
                            no_person = await main.add_detection(snapshot=None, **no_person_args)
                            self.assertTrue(no_person.unaccompanied)
                            no_person_updated = await main.add_detection(
                                snapshot=None, **{**no_person_args, "event_sequence": 1})
                            self.assertTrue(no_person_updated.unaccompanied)
                            self.assertEqual(db.query(Detection).count(), 3)
                    finally:
                        services.SNAPSHOT_DIR = original_dir

            try:
                asyncio.run(run())
                if importlib.util.find_spec("httpx"):
                    from fastapi.testclient import TestClient

                    original_dir = services.SNAPSHOT_DIR
                    services.SNAPSHOT_DIR = Path(directory) / "snapshots"
                    try:
                        with TestClient(main.app) as client:
                            response = client.post("/api/detections", data={
                                "device_id": "CAM-001", "timestamp": datetime.now(timezone.utc).isoformat(),
                                "dog_count": "0", "person_count": "2", "confidence": "0.81",
                                "source": "camera", "event_key": "http-person-1",
                            }, files={"snapshot": ("frame.jpg", b"\xff\xd8test-jpeg", "image/jpeg")})
                            self.assertEqual(response.status_code, 201, response.text)
                            self.assertEqual(response.json()["person_count"], 2)
                            self.assertEqual(response.json()["location"]["name"], "Town Plaza")

                            script_dir = str(Path(__file__).resolve().parents[1] / "scripts")
                            sys.path.insert(0, script_dir)
                            try:
                                spec = importlib.util.spec_from_file_location(
                                    "edge_detector", Path(script_dir) / "07_detect_stream.py")
                                edge = importlib.util.module_from_spec(spec)
                                spec.loader.exec_module(edge)
                            finally:
                                sys.path.remove(script_dir)

                            def deliver(request, timeout):
                                result = client.post("/api/detections", content=request.data,
                                                     headers=dict(request.headers))
                                self.assertEqual(result.status_code, 201, result.text)
                                return BytesIO(result.content)

                            record = {
                                "type": "sighting", "camera_id": "CAM-001", "track_id": 8,
                                "end": datetime.now(timezone.utc).isoformat(), "person_count": 1,
                                "max_conf": .92, "duration_s": 6.0,
                                "max_dogs_in_view": 2, "dogs_together": 2,
                                "snapshot_dog_count": 2,
                                "event_key": "bridge-sighting-8", "event_state": "active",
                                "event_sequence": 0,
                            }
                            args = SimpleNamespace(out=str(Path(directory) / "events.jsonl"),
                                                   device_id="node-1", mqtt_host=None,
                                                   api_url="http://testserver")
                            with patch.object(edge, "urlopen", side_effect=deliver):
                                publisher = edge.Publisher(args)
                                publisher.send("events", record, b"\xff\xd8test-jpeg")
                                publisher.send("events", {**record, "event_sequence": 1,
                                                          "event_state": "closed", "dog_count": 2}, None)
                                publisher.send("events", {**record, "event_key": "bridge-sighting-next",
                                                          "end": (datetime.fromisoformat(record["end"]) + timedelta(minutes=1)).isoformat(),
                                                          "event_sequence": 0, "event_state": "active"},
                                               b"\xff\xd8next-jpeg")
                                publisher.send("events", {**record, "event_key": "bridge-sighting-pack",
                                                          "dogs_together": 4, "max_dogs_in_view": 5,
                                                          "event_sequence": 0},
                                               b"\xff\xd8pack-jpeg")
                            newest = client.get("/api/detections").json()[0]
                            with SessionLocal() as db:
                                next_report = db.query(Detection).filter_by(event_key="bridge-sighting-next").one()
                                self.assertEqual(newest["id"], next_report.id)
                                bridged = db.query(Detection).filter_by(event_key="bridge-sighting-8").one()
                                self.assertEqual(bridged.dog_count, 2)
                                self.assertEqual(bridged.event_state, "closed")
                                self.assertEqual(db.query(Detection).filter_by(event_key="bridge-sighting-8").count(), 1)
                                self.assertEqual(bridged.person_count, 1)
                                self.assertEqual(bridged.dogs_together, 2)
                                self.assertIsNone(bridged.unaccompanied)  # the detector no longer sends it
                                self.assertEqual(bridged.snapshot_dog_count, 2)
                                self.assertIsNotNone(bridged.snapshot_path)
                                pack = db.query(Detection).filter_by(event_key="bridge-sighting-pack").one()
                                self.assertEqual((pack.dogs_together, pack.max_dogs_in_view), (4, 5))
                                bridged_id = bridged.id
                                bridged_snapshot = services.SNAPSHOT_DIR / bridged.snapshot_path.split("/")[-1]

                            deleted = client.delete(f"/api/detections/{bridged_id}")
                            self.assertEqual(deleted.status_code, 200, deleted.text)
                            self.assertFalse(bridged_snapshot.exists())

                            remaining = client.get("/api/detections").json()
                            self.assertEqual(len(remaining), 6)
                            flagged = client.patch(f"/api/detections/{remaining[0]['id']}",
                                                   json={"review_status": "flagged"})
                            self.assertEqual(flagged.status_code, 200, flagged.text)
                            cleared = client.delete("/api/detections")
                            self.assertEqual(cleared.status_code, 200, cleared.text)
                            self.assertEqual(cleared.json()["deleted"], len(remaining))
                            self.assertEqual(client.get("/api/detections").json(), [])
                            self.assertEqual(list(services.SNAPSHOT_DIR.glob("*")), [])
                    finally:
                        services.SNAPSHOT_DIR = original_dir
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()

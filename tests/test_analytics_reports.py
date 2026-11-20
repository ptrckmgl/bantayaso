"""Hotspot limits and the date-range activity report (hour of day, per-zone peak hours)."""

from datetime import datetime, timedelta, timezone
import os
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_saved_url = None


def setUpModule():
    # Import the backend against an in-memory database, never backend/straywatch.db.
    global _saved_url, Base, Detection, Device, Location, MANILA, activity_report, hotspots
    global device_heartbeat, refresh_device_status, OFFLINE_AFTER
    _saved_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite://"
    from backend.database import Base
    from backend.models import Detection, Device, Location
    from backend.services import MANILA, OFFLINE_AFTER, activity_report, device_heartbeat, hotspots, refresh_device_status


def tearDownModule():
    # Let later tests import the backend fresh with their own DATABASE_URL.
    for name in [name for name in sys.modules if name == "backend" or name.startswith("backend.")]:
        del sys.modules[name]
    if _saved_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = _saved_url


class AnalyticsReportTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.plaza = Location(name="Town Plaza", barangay="Poblacion", latitude=0, longitude=0)
        self.market = Location(name="Market", barangay="Poblacion", latitude=0, longitude=0)
        self.db.add_all([self.plaza, self.market])
        self.db.flush()
        self.db.add_all([Device(id="CAM-001", name="Plaza", location_id=self.plaza.id),
                         Device(id="CAM-002", name="Market", location_id=self.market.id)])
        self.count = 0

    def tearDown(self):
        self.db.close()

    def add(self, location, when, dogs, together=None):
        self.count += 1
        device = "CAM-001" if location is self.plaza else "CAM-002"
        self.db.add(Detection(id=f"DET-{self.count}", device_id=device, location_id=location.id,
                              timestamp=when.astimezone(timezone.utc), dog_count=dogs, confidence=.9,
                              dogs_together=together))
        self.db.commit()

    def test_hotspot_reaches_limit_inside_window_only(self):
        now = datetime.now(timezone.utc)
        self.add(self.plaza, now - timedelta(hours=3), 2)
        self.add(self.plaza, now - timedelta(hours=1), 3)
        self.add(self.market, now - timedelta(hours=30), 9)  # outside a 24 h window
        self.add(self.market, now - timedelta(hours=2), 1)

        result = hotspots(self.db, window_hours=24, threshold=5)
        zones = {zone["name"]: zone for zone in result["zones"]}
        self.assertTrue(zones["Town Plaza"]["is_hotspot"])
        self.assertEqual(zones["Town Plaza"]["dogs"], 5)
        self.assertIsNotNone(zones["Town Plaza"]["crossed_at"])
        self.assertFalse(zones["Market"]["is_hotspot"])
        self.assertEqual(zones["Market"]["dogs"], 1)
        self.assertEqual(result["zones"][0]["name"], "Town Plaza")  # hotspots listed first

        self.assertTrue({z["name"]: z for z in hotspots(self.db, 48, 5)["zones"]}["Market"]["is_hotspot"])

    def test_report_groups_by_manila_hour_and_date_range(self):
        day = datetime.now(MANILA).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self.add(self.plaza, day.replace(hour=17, minute=10), 2)
        self.add(self.plaza, day.replace(hour=17, minute=40), 3)
        self.add(self.plaza, day.replace(hour=8), 1)
        self.add(self.market, day.replace(hour=21), 4)
        self.add(self.market, day - timedelta(days=10), 7)  # before the range

        report = activity_report(self.db, (day - timedelta(days=2)).date(), day.date())
        self.assertEqual(report["dogs"], 10)
        self.assertEqual(report["detections"], 4)
        self.assertEqual(len(report["daily"]), 3)
        self.assertEqual(report["hourly"][17]["dogs"], 5)
        self.assertEqual(report["peak_hour"], 17)
        zones = {zone["name"]: zone for zone in report["by_location"]}
        self.assertEqual(zones["Town Plaza"]["peak_hour"], 17)
        self.assertEqual(zones["Market"]["peak_hour"], 21)
        self.assertEqual(zones["Market"]["night_dogs"], 4)
        self.assertEqual(zones["Town Plaza"]["night_dogs"], 0)

    def test_packs_use_dogs_seen_together_not_the_peak(self):
        day = datetime.now(MANILA).replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self.add(self.plaza, day, 4, together=2)   # 4 in one frame, only 2 held together: not a pack
        self.add(self.plaza, day.replace(hour=11), 3, together=3)
        self.add(self.market, day.replace(hour=11), 3)  # scenario or older record: peak count is used
        report = activity_report(self.db, day.date(), day.date(), pack_size=3)
        self.assertEqual(report["packs"], 2)
        self.assertEqual(report["hourly"][11]["packs"], 2)
        self.assertEqual(report["hourly"][10]["packs"], 0)
        zones = {zone["name"]: zone for zone in report["by_location"]}
        self.assertEqual((zones["Town Plaza"]["packs"], zones["Town Plaza"]["largest_group"]), (1, 3))
        self.assertEqual(activity_report(self.db, day.date(), day.date(), pack_size=2)["packs"], 3)

    def test_hotspots_can_count_pack_sightings(self):
        now = datetime.now(timezone.utc)
        self.add(self.plaza, now - timedelta(hours=30), 4, together=4)
        self.add(self.plaza, now - timedelta(hours=2), 3, together=3)
        self.add(self.market, now - timedelta(hours=1), 9, together=2)  # many dogs, never 3 together
        result = hotspots(self.db, window_hours=48, threshold=2, basis="packs", pack_size=3)
        zones = {zone["name"]: zone for zone in result["zones"]}
        self.assertEqual((zones["Town Plaza"]["count"], zones["Town Plaza"]["is_hotspot"]), (2, True))
        self.assertEqual((zones["Market"]["count"], zones["Market"]["is_hotspot"]), (0, False))
        self.assertEqual(zones["Market"]["dogs"], 9)
        self.assertEqual(result["basis"], "packs")
        by_dogs = {z["name"]: z for z in hotspots(self.db, 48, 5, basis="dogs")["zones"]}
        self.assertTrue(by_dogs["Market"]["is_hotspot"])

    def test_camera_goes_offline_when_stopped_or_silent(self):
        self.db.commit()
        self.assertTrue(device_heartbeat(self.db, "CAM-001", "running"))
        self.assertEqual(self.db.get(Device, "CAM-001").status, "online")
        self.assertFalse(device_heartbeat(self.db, "CAM-001", "running"))  # no change
        self.assertFalse(refresh_device_status(self.db))  # heard from just now
        self.db.get(Device, "CAM-001").last_seen = datetime.now(timezone.utc) - OFFLINE_AFTER - timedelta(seconds=1)
        self.db.commit()
        self.assertTrue(refresh_device_status(self.db))
        self.assertEqual(self.db.get(Device, "CAM-001").status, "offline")
        device_heartbeat(self.db, "CAM-001", "running")
        self.assertTrue(device_heartbeat(self.db, "CAM-001", "stopped"))
        self.assertEqual(self.db.get(Device, "CAM-001").status, "offline")
        with self.assertRaises(ValueError):
            device_heartbeat(self.db, "CAM-404", "running")


if __name__ == "__main__":
    unittest.main()

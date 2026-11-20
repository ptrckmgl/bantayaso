"""The detector keeps reports it could not upload and sends them, in order, once the API answers."""

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_detector():
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location("edge_detector_queue", SCRIPTS / "07_detect_stream.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


def report(key, sequence, dogs=1):
    return {"type": "dog_episode", "camera_id": "CAM-001", "event_key": key, "event_sequence": sequence,
            "event_state": "active", "end": "2026-11-20T10:00:00+08:00", "dog_count": dogs,
            "person_count": 0, "max_conf": .9, "duration_s": 2.0, "max_dogs_in_view": dogs,
            "dogs_together": dogs}


def field(body, name):
    marker = f'name="{name}"\r\n\r\n'.encode()
    start = body.index(marker) + len(marker)
    return body[start:body.index(b"\r\n", start)].decode()


class UploadQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.edge = load_detector()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.args = SimpleNamespace(out=str(Path(self.directory.name) / "events.jsonl"), device_id="node-1",
                                    camera_id="CAM-001", mqtt_host=None, api_url="http://api.test")
        self.received = []
        self.api_up = False

    def tearDown(self):
        self.directory.cleanup()

    def fake_urlopen(self, request, timeout):
        if not self.api_up:
            raise URLError("connection refused")
        if request.full_url.endswith("/heartbeat"):
            self.received.append(("heartbeat", json.loads(request.data)["state"]))
        else:
            body = request.data
            self.received.append((field(body, "event_key"), int(field(body, "event_sequence")),
                                  b'name="snapshot"' in body))
        return BytesIO(b"{}")

    def test_reports_wait_on_disk_and_are_sent_in_order_after_an_outage(self):
        with patch.object(self.edge, "urlopen", side_effect=self.fake_urlopen):
            publisher = self.edge.Publisher(self.args)
            self.assertTrue(publisher.send("events", report("A", 0), b"\xff\xd8a"))  # queued counts as accepted
            for sequence in (1, 2, 3):  # updates while the API is down: only the latest is kept
                publisher.send("events", report("A", sequence, dogs=sequence + 1))
            publisher.send("events", report("B", 0), b"\xff\xd8b")
            queued = [(item["record"]["event_key"], item["record"]["event_sequence"]) for item in publisher.pending]
            self.assertEqual(queued, [("A", 0), ("A", 3), ("B", 0)])
            self.assertEqual(len(list(publisher.pending_dir.glob("*.jpg"))), 2)
            self.assertEqual(self.received, [])

            # A restarted detector finds the same queue on disk.
            restarted = self.edge.Publisher(self.args)
            self.assertEqual(len(restarted.pending), 3)

            self.api_up = True
            restarted.heartbeat("running")
            self.assertEqual(self.received, [("heartbeat", "running"), ("A", 0, True), ("A", 3, False), ("B", 0, True)])
            self.assertEqual(restarted.pending, [])
            self.assertEqual(json.loads((restarted.pending_dir / "queue.json").read_text()), [])
            self.assertEqual(list(restarted.pending_dir.glob("*.jpg")), [])

            restarted.send("events", report("C", 0), b"\xff\xd8c")  # queue empty again: sent directly
            self.assertEqual(self.received[-1], ("C", 0, True))

    def test_a_refused_report_is_dropped_not_retried(self):
        def refuse(request, timeout):
            raise HTTPError(request.full_url, 404, "Device not found", None, None)

        with patch.object(self.edge, "urlopen", side_effect=refuse), self.assertLogs(level="ERROR"):
            publisher = self.edge.Publisher(self.args)
            self.assertFalse(publisher.send("events", report("A", 0), b"\xff\xd8a"))
            self.assertEqual(publisher.pending, [])

    def test_stopping_sends_a_stopped_heartbeat_even_while_waiting_to_retry(self):
        with patch.object(self.edge, "urlopen", side_effect=self.fake_urlopen):
            publisher = self.edge.Publisher(self.args)
            publisher.send("events", report("A", 0), b"\xff\xd8a")  # fails, sets the retry wait
            self.api_up = True
            publisher.heartbeat("running")  # skipped: still inside the retry wait
            self.assertEqual(self.received, [])
            publisher.heartbeat("stopped")
            self.assertEqual(self.received, [("heartbeat", "stopped"), ("A", 0, True)])


if __name__ == "__main__":
    unittest.main()

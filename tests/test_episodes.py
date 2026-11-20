"""The camera sends a new image and report each minute of continuous activity."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from episodes import EpisodeReporter


class EpisodeReporterTest(unittest.TestCase):
    def test_group_size_counts_only_after_it_holds_for_two_seconds(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reporter = EpisodeReporter("dog", "node", "CAM-001",
                                   lambda kind, record, image: sent.append(record),
                                   lambda time: False, update_every=100)
        # one frame with a false fourth box, then three dogs held for 2 s
        for second, count in [(0, 4), (1, 3), (2, 3), (3, 3)]:
            reporter.observe(t0 + timedelta(seconds=second), count, 1, .9, capture=lambda: b"image")
        reporter.close()
        self.assertEqual(sent[-1]["max_dogs_in_view"], 4)
        self.assertEqual(sent[-1]["dogs_together"], 3)
        self.assertNotIn("unaccompanied", sent[-1])
        self.assertNotIn("status", sent[-1])

    def test_a_larger_group_sends_an_update_and_a_long_gap_restarts_the_count(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reporter = EpisodeReporter("dog", "node", "CAM-001",
                                   lambda kind, record, image: sent.append(record),
                                   lambda time: False, update_every=100)
        for second in (0, 1, 2):
            reporter.observe(t0 + timedelta(seconds=second), 1, 0, .9, capture=lambda: b"image")
        self.assertEqual(sent[-1]["dogs_together"], 1)
        # three dogs, but with a 3 s detection gap: the count restarts after the gap
        for second, count in [(3, 3), (4, 3), (7, 3), (8, 3)]:
            reporter.observe(t0 + timedelta(seconds=second), count, 0, .9)
        self.assertEqual(sent[-1]["dogs_together"], 1)
        reporter.observe(t0 + timedelta(seconds=9), 3, 0, .9)
        self.assertEqual(sent[-1]["dogs_together"], 3)  # sent at once, not at the next 5 s update
        self.assertEqual(sent[-1]["end"], (t0 + timedelta(seconds=9)).isoformat(timespec="seconds"))
        # first report, the peak rising to 3 in view, then the group of 3 being confirmed
        self.assertEqual([record["dogs_together"] for record in sent], [1, 1, 3])

    def test_continuous_dogs_get_fresh_report_after_interval(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reporter = EpisodeReporter("dog", "node", "CAM-001",
                                   lambda kind, record, image: sent.append((record, image)),
                                   lambda ts: False, update_every=100, snapshot_interval=10)
        for second in range(15):
            reporter.observe(t0 + timedelta(seconds=second), 2, 0, .9,
                             capture=lambda: b"image")
        keys = {record["event_key"] for record, _ in sent}
        self.assertEqual(len(keys), 2)
        self.assertEqual(sum(image is not None for _, image in sent), 2)
        self.assertEqual([record["event_state"] for record, _ in sent],
                         ["active", "closed", "active"])
        self.assertEqual(sent[2][0]["start"], (t0 + timedelta(seconds=12)).isoformat(timespec="seconds"))
        self.assertEqual(sent[2][0]["event_sequence"], 0)
        self.assertTrue(all(record["dog_count"] == 2 for record, _ in sent))

    def test_default_interval_creates_a_second_report_at_one_minute(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reporter = EpisodeReporter("dog", "node", "CAM-001",
                                   lambda kind, record, image: sent.append((record, image)),
                                   lambda ts: False, update_every=120)
        for second in (0, 1, 2, 61, 62):
            reporter.observe(t0 + timedelta(seconds=second), 1, 0, .9,
                             capture=lambda: b"image")
        self.assertEqual([record["event_state"] for record, _ in sent],
                         ["active", "closed", "active"])
        self.assertEqual(sent[0][0]["end"], (t0 + timedelta(seconds=2)).isoformat(timespec="seconds"))
        self.assertEqual(sent[-1][0]["end"], (t0 + timedelta(seconds=62)).isoformat(timespec="seconds"))
        self.assertEqual(sum(image is not None for _, image in sent), 2)

    def test_brief_absence_keeps_count_and_report(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reporter = EpisodeReporter("dog", "node", "CAM-001",
                                   lambda kind, record, image: sent.append((record, image)),
                                   lambda ts: False, snapshot_interval=600)
        for second in range(3):
            reporter.observe(t0 + timedelta(seconds=second), 2, 0, .9,
                             capture=lambda: b"image")
        for second in range(3, 12):
            reporter.observe(t0 + timedelta(seconds=second), 0, 0, 0)
        reporter.observe(t0 + timedelta(seconds=12), 1, 0, .8,
                         capture=lambda: b"image")
        self.assertEqual(len({record["event_key"] for record, _ in sent}), 1)
        self.assertTrue(all(record["dog_count"] == 2 for record, _ in sent))
        self.assertTrue(all(record["event_state"] == "active" for record, _ in sent))

    def test_dogs_keep_one_image_and_close_after_empty_period(self):
        sent = []
        captures = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def capture():
            captures.append(1)
            return b"image"

        reporter = EpisodeReporter("dog", "node", "CAM-001",
                                   lambda kind, record, image: sent.append((record, image)),
                                   lambda ts: False)
        for second, count in [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (6, 2),
                              (7, 2), (8, 2), (9, 2), (10, 2), (11, 2), (12, 0),
                              (17, 0), (21, 0)]:
            reporter.observe(t0 + timedelta(seconds=second), count, 0, .9,
                             capture=capture)
        self.assertEqual(len(captures), 1)
        self.assertEqual([record["event_sequence"] for record, _ in sent], [0, 1, 2, 3])
        self.assertEqual([image for _, image in sent], [b"image", None, None, None])
        self.assertEqual(sent[0][0]["dog_count"], 1)
        self.assertEqual(sent[1][0]["dog_count"], 2)
        self.assertEqual(sent[-1][0]["event_state"], "closed")
        self.assertEqual(len({record["event_key"] for record, _ in sent}), 1)
        reporter.observe(t0 + timedelta(seconds=22), 1, 0, .8, capture=capture)
        reporter.observe(t0 + timedelta(seconds=23), 1, 0, .8, capture=capture)
        reporter.observe(t0 + timedelta(seconds=24), 1, 0, .8, capture=capture)
        self.assertEqual(len({record["event_key"] for record, _ in sent}), 2)

    def test_short_flicker_is_ignored_and_person_period_has_one_image(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reporter = EpisodeReporter("person", "node", "CAM-001",
                                   lambda kind, record, image: sent.append((record, image)),
                                   lambda ts: False)
        reporter.observe(t0, 1, 1, .8, capture=lambda: b"image")
        reporter.observe(t0 + timedelta(seconds=2), 0, 0, 0)
        self.assertEqual(sent, [])
        for second in range(3, 64):
            reporter.observe(t0 + timedelta(seconds=second), 1, 1, .8,
                             capture=lambda: b"image")
        reporter.close()
        self.assertEqual(sum(image is not None for _, image in sent), 1)
        self.assertEqual(len({record["event_key"] for record, _ in sent}), 1)
        self.assertEqual(sent[-1][0]["event_state"], "closed")
        self.assertTrue(all(record["dog_count"] == 0 for record, _ in sent))

    def test_snapshot_is_retried_with_next_metadata_update(self):
        sent = []
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def send(kind, record, image):
            sent.append((record, image))
            return len(sent) > 1

        reporter = EpisodeReporter("dog", "node", "CAM-001", send, lambda ts: False)
        for second in range(13):
            reporter.observe(t0 + timedelta(seconds=second), 1, 0, .9,
                             capture=lambda: b"image")
        self.assertEqual([image for _, image in sent], [b"image", b"image", None])
        self.assertEqual([record["event_sequence"] for record, _ in sent], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()

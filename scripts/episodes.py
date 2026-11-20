"""Camera activity periods with one image per report (replaced when more dogs appear) and periodic fresh reports."""

from uuid import uuid4


class EpisodeReporter:
    def __init__(self, kind, device_id, camera_id, send, is_night,
                 confirm_after=2.0, min_frames=3, empty_after=10.0,
                 update_every=5.0, together_hold=2.0, together_gap=1.0,
                 snapshot_interval=60.0):
        self.kind = kind
        self.device_id = device_id
        self.camera_id = camera_id
        self.send = send
        self.is_night = is_night
        self.confirm_after = confirm_after
        self.min_frames = min_frames
        self.empty_after = empty_after
        self.update_every = update_every
        # A group size counts only after it has held for `together_hold` seconds, allowing
        # detection gaps of up to `together_gap` seconds, so one extra false box is not a pack.
        self.together_hold = together_hold
        self.together_gap = together_gap
        self.snapshot_interval = snapshot_interval
        self.current = None

    def _new(self, ts):
        return {"key": f"{uuid4().hex}-{self.kind}", "start": ts, "last": ts,
                "frames": 0, "peak": 0, "people": 0, "confidence": 0.0,
                "runs": {}, "together": 0, "snapshot": None,
                "snapshot_count": None, "snapshot_delivered": False,
                "created": False, "rotated": False, "sequence": 0,
                "last_emit": None, "first_reported": None, "reported_peak": 0,
                "reported_together": 0}

    def _track_together(self, event, ts, count):
        """Largest number of dogs seen together for at least `together_hold` seconds."""
        runs = event["runs"]
        for size in range(1, count + 1):
            run = runs.get(size)
            if run is None or (ts - run[1]).total_seconds() > self.together_gap:
                runs[size] = [ts, ts]
            else:
                run[1] = ts
            first, last = runs[size]
            if (last - first).total_seconds() >= self.together_hold:
                event["together"] = max(event["together"], size)

    def _record(self, event, state):
        record = {
            "type": f"{self.kind}_episode", "device_id": self.device_id,
            "camera_id": self.camera_id, "event_key": event["key"],
            "event_state": state, "event_sequence": event["sequence"],
            "start": event["start"].isoformat(timespec="seconds"),
            "end": event["last"].isoformat(timespec="seconds"),
            "duration_s": round((event["last"] - event["start"]).total_seconds(), 1),
            "dog_count": event["peak"] if self.kind == "dog" else 0,
            "person_count": event["people"],
            "max_conf": round(event["confidence"], 2),
            "frames": event["frames"], "night": self.is_night(event["start"]),
            "snapshot_dog_count": event["snapshot_count"],
        }
        if self.kind == "dog":
            record.update(dogs_together=event["together"], max_dogs_in_view=event["peak"])
        return record

    def _emit(self, event, state):
        image = event["snapshot"] if not event["snapshot_delivered"] else None
        record = self._record(event, state)
        delivered = self.send("events", record, image)
        event["created"] = True
        if event["first_reported"] is None:
            event["first_reported"] = event["last"]
        if delivered is not False:
            event["snapshot_delivered"] = True
            event["snapshot"] = None
        event["reported_peak"] = event["peak"]
        event["reported_together"] = event["together"]
        event["last_emit"] = event["last"]
        event["sequence"] += 1

    def observe(self, ts, count, person_count, confidence, capture=None):
        """Observe one processed frame. `capture` is called for the first image and, for dogs,
        whenever a frame shows more dogs than the current image."""
        event = self.current
        if count <= 0:
            if event and (ts - event["last"]).total_seconds() >= self.empty_after:
                if event["created"]:
                    self._emit(event, "closed")
                self.current = None
            elif event and not event["created"] and (ts - event["last"]).total_seconds() > 1.0:
                self.current = None  # short flickers do not become reports
            return

        if event is None or (not event["created"] and (ts - event["last"]).total_seconds() > 1.0):
            event = self.current = self._new(ts)
        elif (event["created"] and self.snapshot_interval > 0
              and (ts - event["first_reported"]).total_seconds() >= self.snapshot_interval):
            # Continuous activity has already passed confirmation. Start its next
            # report on this frame so a fresh image appears at the interval.
            self._emit(event, "closed")
            runs = event["runs"]
            event = self.current = self._new(ts)
            event["rotated"] = True
            event["runs"] = runs  # a group that is still together keeps its size in the next report
        event["last"] = ts
        event["frames"] += 1
        event["peak"] = max(event["peak"], count)
        event["people"] = max(event["people"], person_count)
        event["confidence"] = max(event["confidence"], confidence)
        if self.kind == "dog":
            self._track_together(event, ts, count)
        # Keep the image showing the most dogs seen in one frame, so the picture matches the
        # report's peak count. After the report exists, a better image goes with the next update.
        better = event["snapshot_count"] is None or (self.kind == "dog" and count > event["snapshot_count"])
        if capture and better and (not event["created"] or self.kind == "dog"):
            image = capture()
            if image:
                event["snapshot"] = image
                event["snapshot_count"] = count if self.kind == "dog" else 0
                event["snapshot_delivered"] = False

        if not event["created"]:
            if ((event["rotated"] and event["snapshot"] is not None) or
                    (event["frames"] >= self.min_frames
                     and (ts - event["start"]).total_seconds() >= self.confirm_after)):
                self._emit(event, "active")
        elif (event["peak"] > event["reported_peak"]
              or event["together"] > event["reported_together"]
              or (ts - event["last_emit"]).total_seconds() >= self.update_every):
            self._emit(event, "active")

    def close(self):
        """Close a confirmed activity period when the camera process stops."""
        if self.current and self.current["created"]:
            self._emit(self.current, "closed")
        self.current = None

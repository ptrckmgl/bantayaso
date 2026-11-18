"""Camera activity periods with one image per report and periodic fresh reports."""

from uuid import uuid4


class EpisodeReporter:
    def __init__(self, kind, device_id, camera_id, send, is_night,
                 confirm_after=2.0, min_frames=3, empty_after=10.0,
                 update_every=5.0, accompanied_ratio=0.3, stray_confirm=0.0,
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
        self.accompanied_ratio = accompanied_ratio
        self.stray_confirm = stray_confirm
        self.snapshot_interval = snapshot_interval
        self.current = None

    def _new(self, ts):
        return {"key": f"{uuid4().hex}-{self.kind}", "start": ts, "last": ts,
                "frames": 0, "near": 0, "peak": 0, "people": 0, "confidence": 0.0,
                "alone_since": None, "max_alone": 0.0, "snapshot": None,
                "snapshot_count": None, "snapshot_delivered": False,
                "created": False, "rotated": False, "sequence": 0,
                "last_emit": None, "first_reported": None, "reported_peak": 0,
                "reported_unaccompanied": None}

    def _unaccompanied(self, event):
        if self.kind != "dog":
            return None
        # No person was detected anywhere in this report: there is no evidence
        # for calling the dog accompanied, even in a very short report.
        if event["people"] == 0:
            return True
        if event["alone_since"] is None:
            return False
        ratio = event["near"] / event["frames"]
        alone_now = (event["last"] - event["alone_since"]).total_seconds()
        if ratio < self.accompanied_ratio and alone_now >= self.stray_confirm:
            return True
        return None  # a person was seen, but proximity is still being checked

    def _record(self, event, state):
        ratio = event["near"] / event["frames"] if event["frames"] else 0.0
        alone = max(event["max_alone"],
                    (event["last"] - event["alone_since"]).total_seconds()
                    if event["alone_since"] else 0.0)
        unaccompanied = self._unaccompanied(event)
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
            record.update(unaccompanied=unaccompanied,
                          status="UNACCOMPANIED" if unaccompanied is True else
                                 "accompanied" if unaccompanied is False else "checking",
                          accompanied_ratio=round(ratio, 2),
                          max_alone_s=round(alone, 1),
                          max_dogs_in_view=event["peak"])
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
        event["reported_unaccompanied"] = record.get("unaccompanied")
        event["last_emit"] = event["last"]
        event["sequence"] += 1

    def observe(self, ts, count, person_count, confidence, all_near=False, capture=None):
        """Observe one processed frame. `capture` is called only before the first report."""
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
            alone_since = event["alone_since"]
            event = self.current = self._new(ts)
            event["rotated"] = True
            event["alone_since"] = alone_since
        event["last"] = ts
        event["frames"] += 1
        event["peak"] = max(event["peak"], count)
        event["people"] = max(event["people"], person_count)
        event["confidence"] = max(event["confidence"], confidence)
        if self.kind == "dog":
            event["near"] += all_near
            if all_near:
                if event["alone_since"]:
                    event["max_alone"] = max(event["max_alone"],
                                             (ts - event["alone_since"]).total_seconds())
                event["alone_since"] = None
            elif event["alone_since"] is None:
                event["alone_since"] = ts
        if not event["created"] and capture and (event["snapshot"] is None or count > event["snapshot_count"]):
            image = capture()
            if image:
                event["snapshot"] = image
                event["snapshot_count"] = count if self.kind == "dog" else 0

        if not event["created"]:
            if ((event["rotated"] and event["snapshot"] is not None) or
                    (event["frames"] >= self.min_frames
                     and (ts - event["start"]).total_seconds() >= self.confirm_after)):
                self._emit(event, "active")
        elif (event["peak"] > event["reported_peak"]
              or (self.kind == "dog" and self._unaccompanied(event) != event["reported_unaccompanied"])
              or (ts - event["last_emit"]).total_seconds() >= self.update_every):
            self._emit(event, "active")

    def close(self):
        """Close a confirmed activity period when the camera process stops."""
        if self.current and self.current["created"]:
            self._emit(self.current, "closed")
        self.current = None

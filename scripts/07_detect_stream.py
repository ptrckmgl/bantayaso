"""BantayAso edge node: detect, track and count dogs from a camera stream, and emit records.

This is the script the IoT prototype runs (on a laptop now, a Raspberry Pi 5 later).

Sources:
    --source 0                                   laptop webcam
    --source http://192.168.1.5:8080/video       phone running "IP Webcam" (Android)
    --source rtsp://user:pass@10.0.0.20:554/...  existing CCTV camera
    --source data/videos/campus-gate.mp4         recorded clip (for system tests)

    python scripts/07_detect_stream.py --source http://PHONE_IP:8080/video --show
    python scripts/07_detect_stream.py --source clip.mp4 --mqtt-host test.mosquitto.org

One confirmed period of dog activity produces a snapshot and a dashboard report.
Counts and duration update on that report without taking another picture. A continuous
scene gets a fresh report after one minute; an empty scene closes after ten seconds.
Person-only activity follows the same rule.
Each dog report carries "dogs_together": the largest number of dogs seen together for at least
--together-hold seconds. The dashboard calls a report a pack when that number reaches its pack size.
"""
import argparse
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import cv2
from ultralytics import YOLO

from common import RESULTS
from episodes import EpisodeReporter

# Ultralytics prints "Waiting for stream" every time it polls a live camera faster than the
# camera delivers frames (common for webcams in low light). It is harmless, so hide it.
logging.getLogger("ultralytics").addFilter(lambda rec: "Waiting for stream" not in rec.getMessage())


def snapshot_for_result(result):
    """Keep annotated uploads within the API's five-megabyte limit."""
    frame = result.plot()
    height, width = frame.shape[:2]
    if max(height, width) > 1600:
        scale = 1600 / max(height, width)
        frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
    for quality in (75, 55):
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok and len(encoded) <= 5_000_000:
            return encoded.tobytes()
    return None


class Publisher:
    """Writes every record to the JSONL log, optionally to MQTT, and uploads reports to the API.

    Reports that cannot reach the API (it is down, or the network is) are kept in a queue on disk
    next to the log, with their snapshots, and sent oldest first once the API answers again, also
    after a restart. While reports are queued, new reports join the end of the queue so updates
    keep their order. Reports the API refuses (for example an unknown camera ID) are logged and
    dropped, because sending them again would not help.
    """
    RETRY_EVERY = 15.0   # seconds between attempts while the API is unreachable
    MAX_PENDING = 2000   # queued uploads kept at most; the oldest are dropped beyond this

    def __init__(self, args):
        self.out = Path(args.out)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.topic = f"bantayaso/{args.device_id}"
        self.api_url = args.api_url.rstrip("/") if args.api_url else None
        self.camera_id = getattr(args, "camera_id", None)
        self.pending_dir = self.out.with_name(self.out.stem + "_pending")
        self.pending = self._load_pending()
        self.next_retry = 0.0
        if self.pending:
            logging.warning("%d report(s) from an earlier run are waiting in %s", len(self.pending), self.pending_dir)
        self.client = None
        if args.mqtt_host:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.device_id)
            self.client.connect(args.mqtt_host, args.mqtt_port)
            self.client.loop_start()

    # ----- queue of reports waiting for the API -----
    def _queue_file(self):
        return self.pending_dir / "queue.json"

    def _load_pending(self):
        try:
            items = json.loads(self._queue_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [item for item in items if isinstance(item, dict) and isinstance(item.get("record"), dict)]

    def _save_pending(self):
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        temp = self._queue_file().with_suffix(".tmp")
        temp.write_text(json.dumps(self.pending), encoding="utf-8")
        temp.replace(self._queue_file())
        keep = {item["snapshot"] for item in self.pending if item.get("snapshot")}
        for image in self.pending_dir.glob("*.jpg"):
            if image.name not in keep:
                image.unlink(missing_ok=True)

    def _enqueue(self, record, snapshot):
        key = record["event_key"]
        entry = {"record": record, "snapshot": None}
        if snapshot:
            self.pending_dir.mkdir(parents=True, exist_ok=True)
            entry["snapshot"] = f"{key}-{record.get('event_sequence', 0)}.jpg"
            (self.pending_dir / entry["snapshot"]).write_bytes(snapshot)
        same = [i for i, item in enumerate(self.pending) if item["record"].get("event_key") == key]
        # Keep a report's first entry (it carries the snapshot) and only its latest update.
        if len(same) >= 2 and not self.pending[same[-1]].get("snapshot"):
            self.pending[same[-1]] = entry
        else:
            self.pending.append(entry)
        if len(self.pending) > self.MAX_PENDING:
            dropped = len(self.pending) - self.MAX_PENDING
            self.pending = self.pending[dropped:]
            logging.error("Upload queue is full; dropped the %d oldest report(s), still in %s", dropped, self.out)
        self._save_pending()

    def flush(self, force=False):
        """Send queued reports, oldest first, stopping at the first one that cannot get through.
        Returns True when nothing is left waiting."""
        if not self.pending:
            return True
        if not force and time.time() < self.next_retry:
            return False
        sent = 0
        while self.pending:
            item = self.pending[0]
            image = None
            if item.get("snapshot"):
                try:
                    image = (self.pending_dir / item["snapshot"]).read_bytes()
                except OSError:
                    image = None
            if self._upload(item["record"], image) == "retry":
                self.next_retry = time.time() + self.RETRY_EVERY
                break
            self.pending.pop(0)
            sent += 1
        if sent:
            logging.warning("Sent %d queued report(s) to the dashboard; %d still waiting", sent, len(self.pending))
            self._save_pending()
        return not self.pending

    # ----- API calls -----
    def _upload(self, record, snapshot):
        """One upload attempt: 'ok', 'rejected' (the API refused it for good) or 'retry'."""
        fields = {
            "device_id": record["camera_id"], "timestamp": record.get("end", record.get("time")),
            "dog_count": record.get("dog_count", 1), "person_count": record["person_count"],
            "confidence": record["max_conf"], "source": "camera",
            "event_key": record["event_key"],
            "event_state": record.get("event_state", "closed"),
            "event_sequence": record.get("event_sequence", 0),
        }
        if "dogs_together" in record:
            fields.update(duration_s=record["duration_s"],
                          max_dogs_in_view=record["max_dogs_in_view"],
                          dogs_together=record["dogs_together"])
        if "track_id" in record:
            fields["track_id"] = record["track_id"]
        if record.get("snapshot_dog_count") is not None:
            fields["snapshot_dog_count"] = record["snapshot_dog_count"]
        boundary = f"----bantayaso{uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        if snapshot:
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="snapshot"; filename="capture.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
            body.extend(snapshot)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        try:
            request = Request(f"{self.api_url}/api/detections", data=bytes(body),
                              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                              method="POST")
            with urlopen(request, timeout=5) as response:
                response.read()
            return "ok"
        except HTTPError as error:
            if error.code >= 500:
                return "retry"
            logging.error("Dashboard refused report %s: %s; it remains in %s", record["event_key"], error, self.out)
            return "rejected"
        except (URLError, TimeoutError, OSError):
            return "retry"

    def heartbeat(self, state="running"):
        """Tell the API this camera is running (or has stopped), and resend queued reports."""
        if not (self.api_url and self.camera_id):
            return
        if state == "running" and time.time() < self.next_retry:
            return  # the API was unreachable a moment ago; do not stall the video loop
        try:
            request = Request(f"{self.api_url}/api/devices/{self.camera_id}/heartbeat",
                              data=json.dumps({"state": state}).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=3) as response:
                response.read()
        except HTTPError as error:
            logging.warning("Dashboard heartbeat refused for %s: %s", self.camera_id, error)
            return
        except (URLError, TimeoutError, OSError):
            self.next_retry = time.time() + self.RETRY_EVERY
            return
        self.flush(force=True)

    def send(self, kind, record, snapshot=None):
        line = json.dumps(record)
        with open(self.out, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.client:
            # qos=1: the broker acknowledges; paho queues messages while offline
            self.client.publish(f"{self.topic}/{kind}", line, qos=1)
        delivered = True
        if kind == "events" and self.api_url:
            if self.flush():
                result = self._upload(record, snapshot)
                if result == "retry":
                    self._enqueue(record, snapshot)
                    self.next_retry = time.time() + self.RETRY_EVERY
                    logging.warning("Dashboard unreachable; report %s queued in %s and will be resent",
                                    record["event_key"], self.pending_dir)
                delivered = result != "rejected"
            else:
                self._enqueue(record, snapshot)
        print(line)
        return delivered


def body_dog_indices(cls, xyxy, dog_id, person_id, contain=0.6, gap=0.3):
    """Indices of 'dog' boxes that are probably part of a person (a heuristic, off by default).

    A dog box is dropped when
      (a) at least `contain` of its area lies inside a person box (e.g. a dark shirt inside the
          person box), or
      (b) a smaller person box sits on top of it like a head on a torso: the person box's centre
          is above the dog box horizontally, its bottom edge is within `gap` x dog height of the
          dog box's top edge, and it is shorter than the dog box.
    A dog standing next to its owner is kept: it is beside the person's legs, not under the head.
    """
    persons = [b for c, b in zip(cls, xyxy) if c == person_id]
    drop = set()
    for i, (c, d) in enumerate(zip(cls, xyxy)):
        if c != dog_id:
            continue
        dx1, dy1, dx2, dy2 = d
        dw, dh = dx2 - dx1, dy2 - dy1
        area = max(dw * dh, 1e-6)
        for px1, py1, px2, py2 in persons:
            iw = max(0.0, min(dx2, px2) - max(dx1, px1))
            ih = max(0.0, min(dy2, py2) - max(dy1, py1))
            inside = iw * ih / area >= contain
            pcx = (px1 + px2) / 2
            head_on_torso = (dx1 <= pcx <= dx2 and abs(py2 - dy1) <= gap * dh and (py2 - py1) < dh)
            if inside or head_on_torso:
                drop.add(i)
                break
    return drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--weights", default="models/yolo26n_v4.pt",
                    help="trained model (.pt, or an exported _ncnn_model folder / .onnx)")
    ap.add_argument("--conf", type=float, default=0.4, help="dog confidence threshold (use best_conf from 05_evaluate.py)")
    ap.add_argument("--person-conf", type=float, default=None,
                    help="person confidence threshold (default: same as --conf)")
    ap.add_argument("--together-hold", type=float, default=2.0,
                    help="seconds a number of dogs must stay in view together before it counts as "
                         "their group size (stops one false box from making a pack)")
    ap.add_argument("--pack-size", type=int, default=3,
                    help="dogs together shown as a PACK in the preview window (the dashboard has its own setting)")
    # Options of the removed accompanied rule, still accepted so older commands keep working.
    for old in ("--person-memory", "--stray-confirm", "--near-k", "--accompanied-ratio", "--lost-after"):
        ap.add_argument(old, type=float, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--fps", type=float, default=5.0, help="video files: frames processed per second (dogs need ~2-5)")
    ap.add_argument("--live-stride", type=int, default=1, help="live streams: process every Nth frame")
    ap.add_argument("--min-frames", type=int, default=3, help="minimum positive frames before a report")
    ap.add_argument("--confirm-after", type=float, default=2.0, help="seconds of activity before the first report")
    ap.add_argument("--empty-after", type=float, default=10.0, help="seconds without activity before closing a report")
    ap.add_argument("--update-every", type=float, default=5.0, help="seconds between metadata updates; no new image")
    ap.add_argument("--snapshot-interval", type=float, default=60.0,
                    help="seconds of continuous activity before a fresh report and snapshot (0 = off)")
    ap.add_argument("--night-hours", type=int, nargs=2, default=[18, 6], metavar=("FROM", "TO"),
                    help="hours (24 h clock) counted as night for the 'night' field")
    ap.add_argument("--video-start", help="video files: when the clip was filmed, e.g. 2026-11-18T19:30 "
                                          "(default: now), so record times and 'night' match the footage")
    ap.add_argument("--device-id", default="ba-node-01")
    ap.add_argument("--camera-id", default="CAM-001", help="registered dashboard camera ID; its zone supplies the location")
    ap.add_argument("--api-url", default="http://127.0.0.1:8000",
                    help="dashboard backend URL (empty string disables direct upload)")
    ap.add_argument("--heartbeat", type=float, default=60.0,
                    help="seconds between status records; each also tells the dashboard the camera is running")
    ap.add_argument("--mqtt-host")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--out", default=str(RESULTS / "events.jsonl"))
    ap.add_argument("--show", action="store_true", help="show the annotated video")
    ap.add_argument("--suppress-dog-in-person", type=float, default=0.0, metavar="RATIO",
                    help="heuristic, 0 = off: ignore a 'dog' box when more than RATIO of its area lies "
                         "inside a person box, or when it sits directly under a smaller person box "
                         "(head over torso, e.g. a dark shirt). Can also hide a dog being carried.")
    args = ap.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source
    is_file = isinstance(source, str) and Path(source).is_file()
    cap_fps = 30.0
    if is_file:
        cap = cv2.VideoCapture(source)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap_fps = fps if fps and fps > 0 else 30.0  # unreadable files can report 0 or -1
        cap.release()
    # process about --fps frames per second of video; live streams use their own frame rate
    stride = max(1, round(cap_fps / args.fps)) if is_file else args.live_stride
    t0 = datetime.fromisoformat(args.video_start).astimezone() if (is_file and args.video_start) else datetime.now().astimezone()

    def is_night(t):
        start, end = args.night_hours
        return (t.hour >= start or t.hour < end) if start > end else (start <= t.hour < end)

    model = YOLO(args.weights)
    # look the class ids up by name, so a COCO-pretrained model (dog=16, person=0) also works
    name_to_id = {n: i for i, n in model.names.items()}
    DOG, PERSON = name_to_id["dog"], name_to_id["person"]
    person_conf = args.conf if args.person_conf is None else args.person_conf
    infer_conf = min(args.conf, person_conf)  # run at the lower threshold, then filter per class
    tracker = "bytetrack.yaml"
    if infer_conf < 0.25:
        # ByteTrack only starts tracks at >= 0.25 by default, which would hide the extra low-confidence
        # person boxes; use the same settings with the start thresholds lowered to infer_conf.
        import tempfile
        import yaml
        from ultralytics.utils import ROOT
        cfg = yaml.safe_load((ROOT / "cfg" / "trackers" / "bytetrack.yaml").read_text(encoding="utf-8"))
        cfg.update(track_high_thresh=infer_conf, new_track_thresh=infer_conf,
                   track_low_thresh=min(cfg.get("track_low_thresh", 0.1), infer_conf / 2))
        tmp = tempfile.NamedTemporaryFile("w", suffix="_bytetrack.yaml", delete=False, encoding="utf-8")
        yaml.safe_dump(cfg, tmp)
        tmp.close()
        tracker = tmp.name
    pub = Publisher(args)
    pub.heartbeat("running")  # marks the camera online and sends reports queued by an earlier run
    pub.send("status", {"type": "session_start", "device_id": args.device_id, "camera_id": args.camera_id,
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "settings": {"weights": str(args.weights), "dog_conf": args.conf,
                                     "person_conf": person_conf,
                                     "together_hold_s": args.together_hold,
                                     "confirm_after_s": args.confirm_after,
                                     "empty_after_s": args.empty_after,
                                     "update_every_s": args.update_every,
                                     "snapshot_interval_s": args.snapshot_interval,
                                     "suppress_dog_in_person": args.suppress_dog_in_person,
                                     "imgsz": args.imgsz}})
    dogs = EpisodeReporter("dog", args.device_id, args.camera_id, pub.send, is_night,
                           args.confirm_after, args.min_frames, args.empty_after,
                           args.update_every, together_hold=args.together_hold,
                           snapshot_interval=args.snapshot_interval)
    people = EpisodeReporter("person", args.device_id, args.camera_id, pub.send, is_night,
                             args.confirm_after, args.min_frames, args.empty_after,
                             args.update_every, snapshot_interval=args.snapshot_interval)
    last_beat, frame_i, processed, suppressed = 0.0, 0, 0, 0

    def now_ts():
        # video files use video time so system tests are repeatable; live streams use the clock
        return t0 + timedelta(seconds=frame_i / cap_fps) if is_file else datetime.now().astimezone()

    results = model.track(source=source, stream=True, persist=True, tracker=tracker,
                          conf=infer_conf, imgsz=args.imgsz, classes=[DOG, PERSON], verbose=False,
                          vid_stride=stride)
    try:
        for r in results:
            ts = now_ts()
            frame_i += stride
            processed += 1
            if r.boxes is not None and len(r.boxes) and infer_conf < max(args.conf, person_conf):
                # per-class thresholds: dogs need --conf, persons need --person-conf
                keep = [i for i, (c, cf) in enumerate(zip(r.boxes.cls.int().tolist(), r.boxes.conf.tolist()))
                        if cf >= (args.conf if c == DOG else person_conf)]
                if len(keep) < len(r.boxes):
                    r = r[keep]
            if args.suppress_dog_in_person > 0 and r.boxes is not None and len(r.boxes):
                drop = body_dog_indices(r.boxes.cls.int().tolist(), r.boxes.xyxy.tolist(), DOG, PERSON,
                                        contain=args.suppress_dog_in_person)
                if drop:  # removed before the reports and the display
                    suppressed += len(drop)
                    r = r[[i for i in range(len(r.boxes)) if i not in drop]]
            boxes = r.boxes
            cls = boxes.cls.int().tolist() if boxes is not None else []
            xyxy = boxes.xyxy.tolist() if boxes is not None else []
            confs = boxes.conf.tolist() if boxes is not None else []
            visible_person_count = cls.count(PERSON)
            dogs_now = cls.count(DOG)
            dogs.observe(ts, dogs_now, visible_person_count,
                         max((cf for c, cf in zip(cls, confs) if c == DOG), default=0.0),
                         capture=lambda: snapshot_for_result(r))
            # A dog takes precedence over a person-only report. A person-only period
            # continues only when no dog boxes are present.
            people.observe(ts, visible_person_count if not dogs_now else 0,
                           visible_person_count,
                           max((cf for c, cf in zip(cls, confs) if c == PERSON), default=0.0),
                           capture=lambda: snapshot_for_result(r))

            if time.time() - last_beat >= args.heartbeat:
                last_beat = time.time()
                pub.heartbeat("running")
                pub.send("status", {"type": "heartbeat", "device_id": args.device_id,
                                    "camera_id": args.camera_id, "time": ts.isoformat(timespec="seconds"),
                                    "dogs_in_view": dogs_now, "frames_processed": processed,
                                    "dog_boxes_suppressed": suppressed,
                                    "speed_ms": {k: round(v, 1) for k, v in r.speed.items()}})
            if args.show:
                frame = r.plot()
                # group size of the current dog report: the most dogs together for --together-hold s
                together = dogs.current["together"] if dogs.current else 0
                if dogs_now:
                    text = f"{dogs_now} in view, {together} together"
                    color = (0, 140, 255) if together >= args.pack_size else (0, 180, 0)
                    if together >= args.pack_size:
                        text = f"PACK OF {together}  ({dogs_now} in view)"
                    cv2.putText(frame, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
                    cv2.putText(frame, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                cv2.imshow("BantayAso", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        dogs.close()
        people.close()
        pub.heartbeat("stopped")  # the dashboard shows the camera offline at once
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

"""BantayAso edge node: detect, track and count dogs from a camera stream, and emit records.

This is the script the IoT prototype runs (on a laptop now, a Raspberry Pi 5 later).

Sources:
    --source 0                                   laptop webcam
    --source http://192.168.1.5:8080/video       phone running "IP Webcam" (Android)
    --source rtsp://user:pass@10.0.0.20:554/...  existing CCTV camera
    --source data/videos/campus-gate.mp4         recorded clip (for system tests)

    python scripts/07_detect_stream.py --source http://PHONE_IP:8080/video --show
    python scripts/07_detect_stream.py --source clip.mp4 --mqtt-host test.mosquitto.org

Each dog is tracked (ByteTrack) so one dog walking past is ONE sighting, not one per frame.
A dog is "unaccompanied" when no person box is near it for most of the frames it is seen
in. This is our operational stand-in for "stray": the camera cannot see ownership, so the
system flags unaccompanied dog sightings and barangay staff decide (see the stray definition
in docs/dataset_documentation.md). Each record also carries extra evidence (duration, how many
dogs were in view together, night-time) without combining it into a score.

Output: one JSON line per finished sighting in results/events.jsonl, optionally published
to MQTT topic bantayaso/<device-id>/events, plus a status heartbeat every --heartbeat s.
Example record:
  {"type": "sighting", "device_id": "ba-node-01", "camera_id": "cam-1", "track_id": 7,
   "start": "2026-11-21T08:15:02", "end": "2026-11-21T08:15:19", "duration_s": 17.0,
   "unaccompanied": true, "accompanied_ratio": 0.0, "max_conf": 0.91, "frames": 34,
   "max_dogs_in_view": 2, "night": false}
"""
import argparse
import json
import logging
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
from ultralytics import YOLO

from common import RESULTS, RUNS

# Ultralytics prints "Waiting for stream" every time it polls a live camera faster than the
# camera delivers frames (common for webcams in low light). It is harmless, so hide it.
logging.getLogger("ultralytics").addFilter(lambda rec: "Waiting for stream" not in rec.getMessage())


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def is_accompanied(dog_box, person_boxes, k):
    """A person whose centre is within k x (dog box diagonal) of the dog's centre."""
    dx, dy = center(dog_box)
    reach = k * math.hypot(dog_box[2] - dog_box[0], dog_box[3] - dog_box[1])
    return any(math.hypot(px - dx, py - dy) <= reach for px, py in map(center, person_boxes))


class Publisher:
    def __init__(self, args):
        self.out = Path(args.out)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.topic = f"bantayaso/{args.device_id}"
        self.client = None
        if args.mqtt_host:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.device_id)
            self.client.connect(args.mqtt_host, args.mqtt_port)
            self.client.loop_start()

    def send(self, kind, record):
        line = json.dumps(record)
        with open(self.out, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.client:
            # qos=1: the broker acknowledges; paho queues messages while offline
            self.client.publish(f"{self.topic}/{kind}", line, qos=1)
        print(line)


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
    ap.add_argument("--weights", default=str(RUNS / "train" / "yolo26n" / "weights" / "best.pt"),
                    help="trained model (.pt, or an exported _ncnn_model folder / .onnx)")
    ap.add_argument("--conf", type=float, default=0.4, help="dog confidence threshold (use best_conf from 05_evaluate.py)")
    ap.add_argument("--person-conf", type=float, default=None,
                    help="person confidence threshold (default: same as --conf). Lower it so walkers are "
                         "found in more frames; a missed person turns an owned dog into a false 'stray'.")
    ap.add_argument("--person-memory", type=float, default=0.0,
                    help="seconds a person box is remembered after it was last seen, so a person "
                         "flickering out of detection still counts as near the dog (0 = off)")
    ap.add_argument("--stray-confirm", type=float, default=0.0,
                    help="only call a dog 'unaccompanied' if it was also alone for at least this many "
                         "seconds in a row (0 = off)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--fps", type=float, default=5.0, help="video files: frames processed per second (dogs need ~2-5)")
    ap.add_argument("--live-stride", type=int, default=1, help="live streams: process every Nth frame")
    ap.add_argument("--lost-after", type=float, default=5.0, help="seconds unseen before a sighting ends")
    ap.add_argument("--min-frames", type=int, default=3, help="ignore tracks shorter than this (noise)")
    ap.add_argument("--near-k", type=float, default=2.0, help="person within k x dog-box diagonal = with owner")
    ap.add_argument("--accompanied-ratio", type=float, default=0.3,
                    help="share of frames with a person nearby above which the dog counts as accompanied")
    ap.add_argument("--night-hours", type=int, nargs=2, default=[18, 6], metavar=("FROM", "TO"),
                    help="hours (24 h clock) counted as night for the 'night' field")
    ap.add_argument("--video-start", help="video files: when the clip was filmed, e.g. 2026-11-18T19:30 "
                                          "(default: now), so record times and 'night' match the footage")
    ap.add_argument("--device-id", default="ba-node-01")
    ap.add_argument("--camera-id", default="cam-1")
    ap.add_argument("--heartbeat", type=float, default=60.0)
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
    t0 = datetime.fromisoformat(args.video_start) if (is_file and args.video_start) else datetime.now()

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
    pub.send("status", {"type": "session_start", "device_id": args.device_id, "camera_id": args.camera_id,
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "settings": {"weights": str(args.weights), "dog_conf": args.conf,
                                     "person_conf": person_conf, "person_memory_s": args.person_memory,
                                     "stray_confirm_s": args.stray_confirm, "near_k": args.near_k,
                                     "accompanied_ratio": args.accompanied_ratio,
                                     "suppress_dog_in_person": args.suppress_dog_in_person,
                                     "imgsz": args.imgsz}})
    tracks = {}  # id -> dict(start, last, frames, near, max_conf, alone_since, max_alone_s)
    recent_persons = []  # (time, box) of person boxes, kept for --person-memory seconds
    last_beat, frame_i, processed, suppressed = 0.0, 0, 0, 0

    def now_ts():
        # video files use video time so system tests are repeatable; live streams use the clock
        return t0 + timedelta(seconds=frame_i / cap_fps) if is_file else datetime.now()

    def finish(tid, tr):
        if tr["frames"] < args.min_frames:
            return
        ratio = tr["near"] / tr["frames"]
        alone_s = max(tr["max_alone_s"], (tr["last"] - tr["alone_since"]).total_seconds()
                      if tr["alone_since"] else 0.0)
        pub.send("events", {
            "type": "sighting", "device_id": args.device_id, "camera_id": args.camera_id,
            "track_id": int(tid), "start": tr["start"].isoformat(timespec="seconds"),
            "end": tr["last"].isoformat(timespec="seconds"),
            "duration_s": round((tr["last"] - tr["start"]).total_seconds(), 1),
            "unaccompanied": (unacc := ratio < args.accompanied_ratio and alone_s >= args.stray_confirm),
            "status": "UNACCOMPANIED" if unacc else "accompanied",
            "accompanied_ratio": round(ratio, 2), "max_alone_s": round(alone_s, 1),
            "max_conf": round(tr["max_conf"], 2), "frames": tr["frames"],
            "max_dogs_in_view": tr["max_dogs"], "night": is_night(tr["start"])})

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
                if drop:  # removed before the sighting / accompanied logic and the display
                    suppressed += len(drop)
                    r = r[[i for i in range(len(r.boxes)) if i not in drop]]
            boxes = r.boxes
            cls = boxes.cls.int().tolist() if boxes is not None else []
            xyxy = boxes.xyxy.tolist() if boxes is not None else []
            confs = boxes.conf.tolist() if boxes is not None else []
            ids = boxes.id.int().tolist() if boxes is not None and boxes.id is not None else [None] * len(cls)
            persons = [b for c, b in zip(cls, xyxy) if c == PERSON]
            if args.person_memory > 0:
                # remember person boxes for a moment, so a walker who flickers out of detection
                # for a few frames still counts as near the dog
                recent_persons = [(t, b) for t, b in recent_persons
                                  if (ts - t).total_seconds() <= args.person_memory]
                recent_persons += [(ts, b) for b in persons]
                persons = [b for _, b in recent_persons]
            dogs_now = sum(1 for c, tid in zip(cls, ids) if c == DOG and tid is not None)
            for c, b, cf, tid in zip(cls, xyxy, confs, ids):
                if c != DOG or tid is None:
                    continue
                tr = tracks.setdefault(tid, {"start": ts, "last": ts, "frames": 0, "near": 0,
                                             "max_conf": 0.0, "max_dogs": 0,
                                             "alone_since": None, "max_alone_s": 0.0})
                tr["last"], tr["frames"] = ts, tr["frames"] + 1
                near = is_accompanied(b, persons, args.near_k)
                tr["near"] += near
                tr["near_now"] = near
                # longest continuous stretch with no person near (for --stray-confirm)
                if near:
                    if tr["alone_since"]:
                        tr["max_alone_s"] = max(tr["max_alone_s"], (ts - tr["alone_since"]).total_seconds())
                    tr["alone_since"] = None
                elif tr["alone_since"] is None:
                    tr["alone_since"] = ts
                tr["max_conf"] = max(tr["max_conf"], cf)
                tr["max_dogs"] = max(tr["max_dogs"], dogs_now)

            for tid in [t for t, tr in tracks.items() if (ts - tr["last"]).total_seconds() > args.lost_after]:
                finish(tid, tracks.pop(tid))

            if time.time() - last_beat >= args.heartbeat:
                last_beat = time.time()
                pub.send("status", {"type": "heartbeat", "device_id": args.device_id,
                                    "camera_id": args.camera_id, "time": ts.isoformat(timespec="seconds"),
                                    "dogs_in_view": dogs_now, "frames_processed": processed,
                                    "dog_boxes_suppressed": suppressed,
                                    "speed_ms": {k: round(v, 1) for k, v in r.speed.items()}})
            if args.show:
                frame = r.plot()
                # live status under each tracked dog, using the smoothed rule (person memory, stray-confirm):
                # accompanied = a person counts as near right now; checking = alone for less than
                # --stray-confirm s; UNACCOMPANIED = alone for at least --stray-confirm s.
                for c, b, tid in zip(cls, xyxy, ids):
                    if c != DOG or tid not in tracks:
                        continue
                    tr = tracks[tid]
                    alone_now = (ts - tr["alone_since"]).total_seconds() if tr["alone_since"] else 0.0
                    if tr.get("near_now"):
                        text, color = "accompanied", (0, 180, 0)
                    elif alone_now < args.stray_confirm:
                        text, color = f"checking (alone {alone_now:.1f}s)", (0, 200, 255)
                    else:
                        text, color = f"UNACCOMPANIED (alone {alone_now:.0f}s)", (0, 0, 255)
                    org = (int(b[0]), min(frame.shape[0] - 8, int(b[3]) + 22))
                    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
                    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                cv2.imshow("BantayAso", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        for tid, tr in list(tracks.items()):
            finish(tid, tr)
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

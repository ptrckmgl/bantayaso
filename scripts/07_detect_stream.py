"""StrayWatch edge node: detect, track and count dogs from a camera stream, and emit records.

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
in (this is our operational stand-in for "stray"; see the plan doc).

Output: one JSON line per finished sighting in results/events.jsonl, optionally published
to MQTT topic straywatch/<device-id>/events, plus a status heartbeat every --heartbeat s.
Example record:
  {"type": "sighting", "device_id": "sw-node-01", "camera_id": "cam-1", "track_id": 7,
   "start": "2026-11-21T08:15:02", "end": "2026-11-21T08:15:19", "duration_s": 17.0,
   "unaccompanied": true, "accompanied_ratio": 0.0, "max_conf": 0.91, "frames": 34}
"""
import argparse
import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
from ultralytics import YOLO

from common import RESULTS, RUNS


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
        self.topic = f"straywatch/{args.device_id}"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--weights", default=str(RUNS / "train" / "yolo26n" / "weights" / "best.pt"),
                    help="trained model (.pt, or an exported _ncnn_model folder / .onnx)")
    ap.add_argument("--conf", type=float, default=0.4, help="use best_conf from 05_evaluate.py")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--fps", type=float, default=5.0, help="video files: frames processed per second (dogs need ~2-5)")
    ap.add_argument("--live-stride", type=int, default=1, help="live streams: process every Nth frame")
    ap.add_argument("--lost-after", type=float, default=5.0, help="seconds unseen before a sighting ends")
    ap.add_argument("--min-frames", type=int, default=3, help="ignore tracks shorter than this (noise)")
    ap.add_argument("--near-k", type=float, default=2.0, help="person within k x dog-box diagonal = with owner")
    ap.add_argument("--accompanied-ratio", type=float, default=0.3,
                    help="share of frames with a person nearby above which the dog counts as accompanied")
    ap.add_argument("--device-id", default="sw-node-01")
    ap.add_argument("--camera-id", default="cam-1")
    ap.add_argument("--heartbeat", type=float, default=60.0)
    ap.add_argument("--mqtt-host")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--out", default=str(RESULTS / "events.jsonl"))
    ap.add_argument("--show", action="store_true", help="show the annotated video")
    args = ap.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source
    is_file = isinstance(source, str) and Path(source).is_file()
    cap_fps = 30.0
    if is_file:
        cap = cv2.VideoCapture(source)
        cap_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
    # process about --fps frames per second of video; live streams use their own frame rate
    stride = max(1, round(cap_fps / args.fps)) if is_file else args.live_stride
    t0 = datetime.now()

    model = YOLO(args.weights)
    # look the class ids up by name, so a COCO-pretrained model (dog=16, person=0) also works
    name_to_id = {n: i for i, n in model.names.items()}
    DOG, PERSON = name_to_id["dog"], name_to_id["person"]
    pub = Publisher(args)
    tracks = {}  # id -> dict(start, last, frames, near, max_conf)
    last_beat, frame_i, processed = 0.0, 0, 0

    def now_ts():
        # video files use video time so system tests are repeatable; live streams use the clock
        return t0 + timedelta(seconds=frame_i / cap_fps) if is_file else datetime.now()

    def finish(tid, tr):
        if tr["frames"] < args.min_frames:
            return
        ratio = tr["near"] / tr["frames"]
        pub.send("events", {
            "type": "sighting", "device_id": args.device_id, "camera_id": args.camera_id,
            "track_id": int(tid), "start": tr["start"].isoformat(timespec="seconds"),
            "end": tr["last"].isoformat(timespec="seconds"),
            "duration_s": round((tr["last"] - tr["start"]).total_seconds(), 1),
            "unaccompanied": ratio < args.accompanied_ratio, "accompanied_ratio": round(ratio, 2),
            "max_conf": round(tr["max_conf"], 2), "frames": tr["frames"]})

    results = model.track(source=source, stream=True, persist=True, tracker="bytetrack.yaml",
                          conf=args.conf, imgsz=args.imgsz, classes=[DOG, PERSON], verbose=False,
                          vid_stride=stride)
    try:
        for r in results:
            ts = now_ts()
            frame_i += stride
            processed += 1
            boxes = r.boxes
            cls = boxes.cls.int().tolist() if boxes is not None else []
            xyxy = boxes.xyxy.tolist() if boxes is not None else []
            confs = boxes.conf.tolist() if boxes is not None else []
            ids = boxes.id.int().tolist() if boxes is not None and boxes.id is not None else [None] * len(cls)
            persons = [b for c, b in zip(cls, xyxy) if c == PERSON]
            dogs_now = 0
            for c, b, cf, tid in zip(cls, xyxy, confs, ids):
                if c != DOG or tid is None:
                    continue
                dogs_now += 1
                tr = tracks.setdefault(tid, {"start": ts, "last": ts, "frames": 0, "near": 0, "max_conf": 0.0})
                tr["last"], tr["frames"] = ts, tr["frames"] + 1
                tr["near"] += is_accompanied(b, persons, args.near_k)
                tr["max_conf"] = max(tr["max_conf"], cf)

            for tid in [t for t, tr in tracks.items() if (ts - tr["last"]).total_seconds() > args.lost_after]:
                finish(tid, tracks.pop(tid))

            if time.time() - last_beat >= args.heartbeat:
                last_beat = time.time()
                pub.send("status", {"type": "heartbeat", "device_id": args.device_id,
                                    "camera_id": args.camera_id, "time": ts.isoformat(timespec="seconds"),
                                    "dogs_in_view": dogs_now, "frames_processed": processed,
                                    "speed_ms": {k: round(v, 1) for k, v in r.speed.items()}})
            if args.show:
                cv2.imshow("StrayWatch", r.plot())
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

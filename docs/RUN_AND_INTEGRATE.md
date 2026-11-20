# Run the BantayAso model and connect it to the dashboard

For anyone (or any AI assistant) asked to "run the model" or "connect it to the dashboard".
Everything below was tested on Windows 11 with Python 3.14, PyTorch 2.14 (CUDA) and Ultralytics 8.4.

## What you have

| File | What it is |
|---|---|
| `models/yolo26n_v4.pt` | **Final model.** YOLO26n, classes `dog` (0) and `person` (1). Use this one. |
| `models/yolo26n_v3.pt` | Backup (earlier model, trained on data whose test split shared cameras with training). |
| `scripts/07_detect_stream.py` | The edge node: reads a camera/stream/video, detects dogs and people, and creates fresh snapshot reports each minute of continuous activity. |

The model only finds dogs and people in an image. `07_detect_stream.py` counts how many dogs stay in
view together (`dogs_together`); the dashboard calls a report a pack when that count reaches its pack size.

## 1. Setup (once)

```powershell
python -m venv .venv
.venv\Scripts\activate
# for GPU acceleration, install the matching PyTorch CUDA build first
pip install -r backend/requirements.txt -r requirements-inference.txt
```

Only `ultralytics`, `lap` (tracker), `pyyaml` and `paho-mqtt` are needed to run the detector;
the other packages in `requirements.txt` are for dataset building.

## 2. Run it

```powershell
# a video file (the easiest first test; frames are processed at --fps, default 2-5 is enough)
python scripts/07_detect_stream.py --weights models/yolo26n_v4.pt --source clip.mp4 --show

# laptop webcam
python scripts/07_detect_stream.py --weights models/yolo26n_v4.pt --source 0 --show

# phone camera: install "IP Webcam" (Android), tap Start server, laptop on the SAME Wi-Fi
python scripts/07_detect_stream.py --weights models/yolo26n_v4.pt --source http://PHONE_IP:8080/video --show
```

Recommended detector settings (the ones used in testing):
`--conf 0.35 --person-conf 0.20 --suppress-dog-in-person 0.6`. A group size counts after it holds for
2 seconds (`--together-hold 2`). The old `--person-memory`, `--stray-confirm`, `--near-k` and
`--accompanied-ratio` options are still accepted but do nothing.
Press `q` in the video window to stop. Without `--show` there is no window; stop with Ctrl-C.
For recorded video also pass `--video-start 2026-11-18T19:30` (when it was filmed) so the
record times and the `night` field match the footage.

Output goes to `results/events.jsonl` (one JSON per line) and is printed to the console.

## 3. Connect to the dashboard (HTTP)

Start the FastAPI backend and React dashboard as shown in the README. Register the camera and
its monitoring zone in the dashboard. Then run the detector with that exact camera ID:

```powershell
bat\webcam_v4 --camera-id CAM-001
```

The detector confirms an activity period after 2 seconds and at least 3 processed frames.
It posts one annotated JPEG and an `active` report to `/api/detections`. While activity
continues, it updates that same report about every 5 seconds without another image. A brief
absence keeps the report open and never changes its peak dog count to zero. After 10 seconds
without a dog, the report becomes `closed`; a later arrival starts a new report. When dogs
remain visible continuously, a new report with a fresh snapshot starts every minute and appears
above the older report in detection history.
Person-only periods follow the same rule when no dog is visible. Change the defaults with
`--confirm-after`, `--min-frames`, `--update-every`, `--empty-after`, and
`--snapshot-interval` (seconds, default 60; 0 disables periodic fresh reports).

For a dog report, `dog_count` and `max_dogs_in_view` are the peak number of dog boxes
visible together during that report. `snapshot_dog_count` is the number in the one saved
image. The two may differ if more dogs appear after that image. Dashboard totals add peak
counts across reports; they are not counts of unique animals, including when one dog remains
visible across multiple one-minute reports. The API attaches the
registered camera's location and preserves its snapshot and review status during updates.
The web page refreshes every 15 seconds.

Use `--api-url http://HOST:8000` when the API runs on another machine. An empty `--api-url ''`
disables HTTP upload. If an upload fails after a retry, the detector logs the failure and leaves
event metadata in its JSONL output (the helper uses `results/v4/events_webcam.jsonl`). The
snapshot is retried with the next update while that report remains open. If connectivity has not
returned before the report closes, rerun a recorded clip or resubmit the event before relying
on dashboard totals. A camera ID that is not registered
receives HTTP 404.

## 4. Optional MQTT output

Add `--mqtt-host <broker address>` (and `--mqtt-port`, default 1883). The detector then also
publishes each record, QoS 1, to:

| Topic | When | Content |
|---|---|---|
| `bantayaso/<device-id>/events` | one initial record, metadata updates, and one close record per confirmed period | the activity record below |
| `bantayaso/<device-id>/status` | start of a session, then every `--heartbeat` s (default 60) | `session_start` and `heartbeat` records (dogs in view, frames processed, speed in ms) |

`<device-id>` is set with `--device-id` (default `ba-node-01`); `--camera-id` names the camera
(default `CAM-001`). A public test broker such as `test.mosquitto.org` works for a demo, but anyone
can read it: use your own broker for real data.

MQTT is an additional output. The dashboard's built-in ingestion uses HTTP, not an MQTT subscriber.

### Activity record (one dashboard row per `event_key`)

```json
{"type": "dog_episode", "device_id": "ba-node-01", "camera_id": "CAM-001",
 "event_key": "unique-period-key", "event_state": "active", "event_sequence": 0,
 "start": "2026-11-21T08:15:02", "end": "2026-11-21T08:15:04", "duration_s": 2.0,
 "dog_count": 2, "person_count": 0, "snapshot_dog_count": 2,
 "dogs_together": 2, "max_conf": 0.91,
 "frames": 3, "max_dogs_in_view": 2, "night": false}
```

| Field | Meaning |
|---|---|
| `dogs_together` | most dogs that stayed in view together for at least `--together-hold` seconds (default 2); the dashboard calls the report a pack when this reaches its pack size (default 3) |
| `duration_s`, `start`, `end` | how long the activity was observed |
| `max_dogs_in_view` | most dogs in any single frame; can include a brief false box, so packs use `dogs_together` |
| `night` | activity started 18:00 to 06:00 (or per `--night-hours`) |
| `max_conf` | detector's best confidence for the dog |
| `event_key`, `event_sequence` | report identity and increasing update number; repeated or older updates do not create extra rows |
| `event_state` | `active` until the scene has been empty for 10 seconds or the one-minute snapshot interval ends, then `closed` |

Repeat activity at the same place on several days can indicate a hotspot. The system cannot recognise
an individual dog, so one animal can appear in multiple reports.

## 5. Test the whole chain without a camera

```powershell
python scripts/07_detect_stream.py --source clip.mp4 --camera-id CAM-001
```

Open the dashboard's Detections page to see the snapshots and review them.

## Troubleshooting

- `cannot open source`: the stream address is wrong, or the phone and laptop are on different
  Wi-Fi networks (or the Wi-Fi blocks device-to-device traffic; a phone hotspot usually works).
- Very slow: PyTorch is the CPU build. Check `python -c "import torch; print(torch.cuda.is_available())"`.
- CUDA out of memory: close other GPU programs; the detector itself only needs about 1 GB.
- Windows crashes while loading: not an issue for the detector (it is for training: use `--workers 2`).
- Dog boxes on a dark shirt or carried dogs vanish: that is `--suppress-dog-in-person`; set it to 0 to turn it off.
- Know the limits: it does not see ownership, so it reports group size, not whether dogs are strays.
  A dog hidden behind another, or missed by the model, lowers the count.

## Metrics (for context)

v4 test (1,542 images, cameras never seen in training): precision 0.76, recall 0.63, F1 0.69,
mAP50 0.70 (dog AP50 0.81, person AP50 0.60). Details: `results/v4/v4_report.md` and
`docs/dataset_documentation.md`.

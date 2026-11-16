# Run the BantayAso model and connect it to the dashboard

For anyone (or any AI assistant) asked to "run the model" or "connect it to the dashboard".
Everything below was tested on Windows 11 with Python 3.14, PyTorch 2.14 (CUDA) and Ultralytics 8.4.

## What you have

| File | What it is |
|---|---|
| `models/yolo26n_v4.pt` | **Final model.** YOLO26n, classes `dog` (0) and `person` (1). Use this one. |
| `models/yolo26n_v3.pt` | Backup (earlier model, trained on data whose test split shared cameras with training). |
| `scripts/07_detect_stream.py` | The edge node: reads a camera/stream/video, detects, tracks dogs, decides "unaccompanied", writes one JSON record per dog sighting. |

The model only finds dogs and people in an image. The "stray" decision (a dog with no person
near it) is made in `07_detect_stream.py`, so the dashboard receives finished **sighting
records**, not raw boxes.

## 1. Setup (once)

```powershell
python -m venv .venv
.venv\Scripts\activate
# install PyTorch FIRST using the command from https://pytorch.org/get-started/locally/
# (a plain `pip install torch` on Windows gives the CPU-only build; CPU works but is slow)
pip install -r requirements.txt
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
`--conf 0.35 --person-conf 0.20 --person-memory 2 --stray-confirm 3 --suppress-dog-in-person 0.6`.
Press `q` in the video window to stop. Without `--show` there is no window; stop with Ctrl-C.
For recorded video also pass `--video-start 2026-11-18T19:30` (when it was filmed) so the
record times and the `night` field match the footage.

Output goes to `results/events.jsonl` (one JSON per line) and is printed to the console.

## 3. Connect to the dashboard (MQTT)

Add `--mqtt-host <broker address>` (and `--mqtt-port`, default 1883). The detector then also
publishes each record, QoS 1, to:

| Topic | When | Content |
|---|---|---|
| `bantayaso/<device-id>/events` | one per finished dog sighting | the sighting record below |
| `bantayaso/<device-id>/status` | start of a session, then every `--heartbeat` s (default 60) | `session_start` and `heartbeat` records (dogs in view, frames processed, speed in ms) |

`<device-id>` is set with `--device-id` (default `ba-node-01`); `--camera-id` names the camera
(default `cam-1`). A public test broker such as `test.mosquitto.org` works for a demo, but anyone
can read it: use your own broker for real data.

Subscribe from the dashboard side to `bantayaso/+/events` to receive all devices.

### Sighting record (the thing the dashboard stores)

```json
{"type": "sighting", "device_id": "ba-node-01", "camera_id": "cam-1", "track_id": 7,
 "start": "2026-11-21T08:15:02", "end": "2026-11-21T08:15:19", "duration_s": 17.0,
 "unaccompanied": true, "status": "UNACCOMPANIED", "accompanied_ratio": 0.0, "max_conf": 0.91,
 "frames": 34, "max_dogs_in_view": 2, "night": false}
```

| Field | Meaning |
|---|---|
| `unaccompanied` | `true` = no person was near the dog for most of the sighting (our stand-in for "stray"; staff decide) |
| `accompanied_ratio` | share of frames with a person near the dog (below 0.3 = unaccompanied) |
| `duration_s`, `start`, `end` | how long the dog was in view (passing by vs lingering) |
| `max_dogs_in_view` | dogs seen together (a pack) |
| `night` | sighting started 18:00 to 06:00 (or per `--night-hours`) |
| `max_conf` | detector's best confidence for the dog |
| `track_id` | tracker id, only meaningful within one run |

Repeat sightings of the same place on several days make a hotspot. The system cannot recognise
an individual dog, so the same dog passing twice is two sightings.

## 4. Test the whole chain without a camera

```powershell
python scripts/07_detect_stream.py --weights models/yolo26n_v4.pt --source clip.mp4 --mqtt-host test.mosquitto.org
```

then subscribe with any MQTT client (for example `mosquitto_sub -h test.mosquitto.org -t "bantayaso/#" -v`).

## Troubleshooting

- `cannot open source`: the stream address is wrong, or the phone and laptop are on different
  Wi-Fi networks (or the Wi-Fi blocks device-to-device traffic; a phone hotspot usually works).
- Very slow: PyTorch is the CPU build. Check `python -c "import torch; print(torch.cuda.is_available())"`.
- CUDA out of memory: close other GPU programs; the detector itself only needs about 1 GB.
- Windows crashes while loading: not an issue for the detector (it is for training: use `--workers 2`).
- Dog boxes on a dark shirt or carried dogs vanish: that is `--suppress-dog-in-person`; set it to 0 to turn it off.
- Know the limits: it does not see ownership, so a stray next to a passer-by counts as
  accompanied; unaccompanied is a flag for staff to check.

## Metrics (for context)

v4 test (1,542 images, cameras never seen in training): precision 0.76, recall 0.63, F1 0.69,
mAP50 0.70 (dog AP50 0.81, person AP50 0.60). Details: `results/v4/v4_report.md` and
`docs/dataset_documentation.md`.

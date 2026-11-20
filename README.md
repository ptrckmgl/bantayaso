# BantayAso: Python API + monitoring dashboard

This repository includes a React monitoring dashboard and a trained dog/person detector. The detector runs on a camera, webcam, phone stream, or video file and sends snapshots and observations to the Python API. Python stores the events, camera location, review state, and analytics. The dashboard can also generate clearly labeled example events without a camera.

```text
Camera/video -> YOLO26n + tracking -> image + metadata -> FastAPI -> SQLite + snapshots
Simulator ---------------------------------------------> FastAPI -> React dashboard
```

## Run the dashboard locally

Use Python 3.11 or newer and Node.js 20 or newer. The commands below are for **Windows Command Prompt**. `cd /d` switches from `C:` to the project on `D:`.

First-time setup:

```cmd
cd /d D:\bantayaso
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r requirements-inference.txt
cd /d D:\bantayaso\frontend
npm.cmd install
```

On each run, start the backend in **Terminal 1**:

```cmd
cd /d D:\bantayaso
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Start the website in **Terminal 2**:

```cmd
cd /d D:\bantayaso\frontend
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. The Python API is at **http://127.0.0.1:8000/docs**. Vite proxies `/api` and `/snapshots` to FastAPI. Keep both terminals open while using the dashboard. If a review action says the local API is unavailable, restart the backend command in Terminal 1. In PowerShell, use `cd D:\bantayaso` (without `/d`); the other commands are the same.

On a fresh database, the first API startup creates `backend/straywatch.db` with **one example location and camera** (`CAM-001` at Town Plaza), and **zero detections and snapshots**. The dashboard explains the camera → API → storage → review flow and refreshes every 15 seconds. Click **Generate one example event** to create a single Python generated snapshot and detection record, or send one through the device ingestion endpoint with the IoT simulator:

```powershell
.venv\Scripts\python.exe -m iot.simulator --device CAM-001 --dogs 2
```

The simulator requires the API to be running. Change `--device` to any registered camera ID, or use **Generate example event for this camera** on a camera card. It uses Pillow to draw a clearly labeled **still frame**, with no camera or model needed. Simulated events do not mark a physical camera as online.

To send real model observations, follow the camera steps below. The helper selects `models/yolo26n_v4.pt` and the tested detection settings; its default API is `http://127.0.0.1:8000`.

## Add and run a camera

1. Keep the backend and website running in their own terminals, then open **http://127.0.0.1:5173**.
2. In **CCTV Cameras → Add camera**, enter a unique ID such as `CAM-002` and a name. Choose an existing monitoring zone or create a new one. The zone gives future detections their location. `CAM-001` at Town Plaza is already registered as an example.
3. Open a third Command Prompt terminal and run the camera using the same ID you registered. The first-time setup above installs the detector packages:

   ```cmd
   cd /d D:\bantayaso
   .\bat\webcam_v4.bat --camera-id CAM-002 --source 0 --out results\v4\events_CAM-002.jsonl
   ```

   To use the already registered `CAM-001` with the first webcam instead, run `.\bat\webcam_v4.bat --camera-id CAM-001`.

   `--camera-id` identifies the dashboard record; `--source` selects the actual video input. `0` is usually the laptop's first webcam. If `CAM-001` already uses that webcam, a second detector needs a different physical source. For a second USB webcam, use `--source 1` if Windows assigned it that index:

   ```cmd
   .\bat\webcam_v4.bat --camera-id CAM-002 --source 1 --out results\v4\events_CAM-002.jsonl
   ```

   For a network camera, replace `1` with its stream URL, for example `--source "rtsp://USER:PASSWORD@CAMERA_IP:554/stream"`. Use a separate detector terminal and output file for each camera running at the same time.
4. Watch the preview for dog and person boxes. After a dog has appeared for at least **2 seconds and 3 processed frames**, the detector creates a report with one snapshot. It updates that report's peak counts and duration about every **5 seconds**, without another picture. A brief disappearance does not reset the report's dog count to zero. After **10 seconds without a dog**, it closes the report; a later arrival starts a new one. If dogs stay continuously, it creates a **new report with a fresh snapshot every minute**. Each new report appears above the older one in detection history. Person-only activity follows the same rule when no dog is visible. The Detections page refreshes every 15 seconds. Press **q** in the preview to stop the detector; press **Ctrl+C** in the backend and website terminals to stop those servers.

On **CCTV Cameras**, select a camera card to open its details, location, latest snapshot, and detection history within the CCTV section. **Open in Detections** shows the same camera's records with its location selected; **All detections** returns to the full history. A camera with no events shows an empty history for that camera.

Registering a camera only saves its ID, name, and zone; it does not start a feed. It begins **offline** and changes to **online** as soon as its detector starts: the detector sends a heartbeat at start-up and with every status record (`--heartbeat`, 5 seconds in the launch scripts). It turns **offline** at once when the detector stops normally, and after 2 minutes without any signal if the detector or its network fails (`CAMERA_OFFLINE_AFTER_S` on the API). The camera card shows the latest saved snapshot, not continuous live video.

For camera reports, `dog_count` is the **maximum dogs visible together during that report**. `snapshot_dog_count` is the count in its saved image; it may differ if more dogs appear later. Dashboard totals sum peak counts across reports, so they are **not a count of unique dogs**: a dog visible across two one-minute reports can appear in both totals. Adjust the timing with `--confirm-after`, `--empty-after`, `--update-every`, and `--snapshot-interval 60` (seconds). If no event appears, check that the API is running at **http://127.0.0.1:8000/api/health**, the `--camera-id` exactly matches a registered camera, and `--source` points to a working camera. Reports that cannot reach the API are queued with their snapshots in a `<log name>_pending` folder next to the JSONL output and sent, oldest first, once the API answers again, also after the detector restarts. Reports the API refuses (for example an unknown camera ID) are logged and not retried. More settings and limitations are in `docs/RUN_AND_INTEGRATE.md`.

Each dog report also carries `dogs_together`: the most dogs that stayed in view together for at least 2 seconds (`--together-hold`), so one extra false box in a single frame does not inflate it. When `dogs_together` reaches the **pack size** (3 by default, set in **Settings**), the dashboard labels the report **Pack of N**, lists it under **Packs only** in Detections, and counts it in the Analytics pack figures. Scenario events and older reports have no sustained count, so their peak count is used. The system does not judge whether dogs have owners: a camera cannot tell an owner from a passer-by, so it only reports what it sees.

### Dashboard features

- API-backed totals, seven day trends, and recent captures after events arrive.
- Searchable, filterable detection history with review, flag, individual delete, delete all, details, and CSV export.
- An in-app notification bell for recent detections awaiting review. Open a notice to inspect its report, mark notices read, dismiss one with **X**, or use **Clear all**. Read and dismissed state is saved in this browser; clearing notices does not delete detections or change review status.
- CCTV device list and registration, with connectivity state and a choice of an existing or newly created monitoring zone.
- Analytics by day and monitoring zone.
- Responsive layout and persistent light/dark mode.

### API and storage

FastAPI routes include `/api/dashboard/summary`, `/api/devices`, `/api/devices/{device_id}`, `/api/detections`, `/api/detections/{detection_id}`, `/api/locations`, `/api/analytics`, `/api/analytics/report` (with `start`, `end` and `pack_size`), `/api/hotspots`, `/api/revision`, and `/api/demo/simulate`. Camera registration accepts an existing `location_id` or a `new_location` object containing a zone name, barangay, and optional description; both camera and new zone are saved together. `POST /api/locations` can also register a zone by itself. `POST /api/detections` accepts `multipart/form-data` fields `device_id`, `timestamp` (ISO 8601), `dog_count`, `confidence`, `source`, and optional `snapshot` (PNG, JPEG, or WebP; maximum 5 MB). Camera uploads can also include `person_count`, `track_id`, `duration_s`, `max_dogs_in_view`, `dogs_together`, `snapshot_dog_count`, `event_state` (`active` or `closed`), `event_sequence` (increasing integer), and a unique `event_key` (the older `unaccompanied` and `accompanied_ratio` fields are still accepted and stored but no longer shown). A later sequence with the same key updates counts and state on the existing report while keeping its snapshot and review status. Detection and device records are stored with SQLAlchemy in SQLite, with `DATABASE_URL` available to point at PostgreSQL later. Snapshot file references are stored in the database and served from `/snapshots/`. Review status is updated with `PATCH /api/detections/{detection_id}`. `DELETE /api/detections/{detection_id}` deletes one record, and `DELETE /api/detections` deletes all records, regardless of review status. Both remove snapshots no longer referenced by a record; cameras and locations remain. The dashboard asks for confirmation before either delete action.

The prototype does not authenticate operators or devices. Add authentication, device credentials, and production migration tooling before real deployment.

## Existing ML work

The machine learning part of **BantayAso**, an IoT system that helps barangays monitor stray dogs.
A YOLO26n object detector finds `dog` and `person` in camera frames. The detector groups frames
into activity periods and records how many dogs stay together, so the dashboard can flag **packs**
(3 or more dogs together by default). Activity records and their first snapshots go directly to the dashboard
API. MQTT remains available as an optional additional output.

```
camera / phone / CCTV -> edge node (07_detect_stream.py) -> HTTP API -> dashboard
                         YOLO26n + ByteTrack + dogs-together count
                         (optional: also publish records through MQTT)
```

COSC 105 (Intelligent Systems) component, BSCS 4-1 Group 4.

## Repository layout

| Path | What it is |
| --- | --- |
| `configs/sources.yaml` | Every dataset used, with its license |
| `configs/classes.yaml` | Our two classes and how source class names map to them |
| `scripts/01_download_public.py` | Dog/person subsets of Open Images V7 and COCO 2017 (FiftyOne) |
| `scripts/02_download_roboflow.py` | Roboflow Universe stray dog datasets |
| `scripts/extract_frames.py` | Our own phone videos to frames for labeling |
| `scripts/03_merge_datasets.py` | Cleaning, class mapping, deduplication, train/val/test split, stats |
| `scripts/04_train.py` | Trains YOLO26n, YOLOv5n and YOLO11n with identical settings |
| `scripts/05_evaluate.py` | Precision, recall, F1, mAP, speed, confusion matrix; comparison table |
| `scripts/06_export.py` | Export to NCNN (Raspberry Pi), ONNX (laptop), TFLite (Android), CoreML (iPhone) |
| `scripts/07_detect_stream.py` | The edge node: live detection, activity reports, MQTT |
| `docs/dataset_documentation.md` | Dataset and ML documentation template (follows the course guide, section D) |
| `results/` | Generated tables and logs for the paper (committed) |
| `data/`, `runs/` | Datasets and training outputs (not committed, too large) |

## 1. Setup (Windows, NVIDIA RTX 4060)

1. Update the NVIDIA driver and install Python 3.11 or 3.12.
2. Create a virtual environment in this folder:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Install PyTorch **with CUDA** using the command from <https://pytorch.org/get-started/locally/>
   (choose Stable, Windows, Pip, Python, the newest CUDA). A plain `pip install torch` installs
   the CPU-only build.
4. Install the rest: `pip install -r requirements.txt`
5. Check the GPU is visible: `python -c "import torch; print(torch.cuda.is_available())"` must print `True`.

All commands below are run from the repository root.

## 2. Get the public data

```powershell
python scripts/01_download_public.py --max-samples 200   # quick test first
python scripts/01_download_public.py                      # full download (see sources.yaml)

$env:ROBOFLOW_API_KEY="your_key"                          # roboflow.com -> Settings -> API Keys
python scripts/02_download_roboflow.py
```

Before downloading a Roboflow set, open its page, check the license and the latest version
number, and update `configs/sources.yaml`. Add more sets the same way.

## 3. Add our own footage (campus / street dogs)

1. Film short clips (10 to 60 s) from about 2.5 to 3 m high, looking down like a mounted camera,
   at different times (morning, noon, dusk, night) and places. Name each file
   `<place>_<date>_<time>.mp4`, e.g. `campus-gate_2026-11-18_am.mp4`, and put them in `data/videos/`.
2. `python scripts/extract_frames.py data/videos --fps 1` -> `data/frames/`
3. Upload `data/frames/` to a Roboflow project with classes `dog` and `person`. Use the
   pretrained model's auto-label to draw first-pass boxes, then correct every frame by hand.
   Blur faces if the images will be shared.
4. Export from Roboflow in **YOLOv8** format and unzip it into `data/raw/own/`.

## 4. Merge and split

```powershell
python scripts/03_merge_datasets.py                    # own footage = test set only (phase 1)
python scripts/03_merge_datasets.py --own-mode split   # later: also fine-tune on own clips

# the settings used for the final model (v4): leakage-free split + thinning of repeated frames
python scripts/03_merge_datasets.py --split-by-scene --thin-repeats 10
```

Public data is split 75/15/10 by group. With `--split-by-scene`, all frames of one camera or
video (read from the file name) stay in one split, and `--thin-repeats 10` drops a frame only
when an earlier frame of the same camera looks almost the same and has the same number of dog
and person boxes. Own footage is split **by clip**, so frames of one clip
never appear in both training and testing. `scripts/pseudo_label_persons.py` adds missing
`person` boxes to the lr3 set (run it before merging). Counts go to `results/dataset_stats.csv` and every
cleaning action to `results/cleaning_log.csv` (both are for the paper).

## 5. Train

```powershell
python scripts/04_train.py --epochs 3 --fraction 0.1   # 5-minute smoke test
python scripts/04_train.py                             # all three models, 100 epochs, early stopping
# the final model (v4), about 1.8 h on an RTX 4060 laptop:
python scripts/04_train.py --models yolo26n.pt --tag v4 --epochs 50 --patience 10 --batch 16 --workers 4
```

If Windows crashes while loading data, add `--workers 2` (or `0`). Keep a laptop plugged in.
Each run saves `runs/train/<model>/` with `weights/best.pt`, loss and mAP curves, and the
confusion matrix.

## 6. Evaluate

```powershell
python scripts/05_evaluate.py                                                  # test set in data.yaml
python scripts/05_evaluate.py --data data/merged/data_public_test.yaml --tag public
```

Report both: the public test split and the real-world test on our own footage. The gap between
them is worth discussing in the paper. Tables land in `results/comparison_<tag>.md`.

## 7. Run the edge node

```powershell
# the .bat helpers live in the bat folder (run from the repo root; press q in the video window to stop)
bat\webcam_v4                # laptop webcam, final model (v4); bat\webcam_v3 is the earlier model
bat\webcam_v4 --source http://PHONE_IP:8080/video      # phone camera

# compare v3 (left) and v4 (right) on the same frames; saves a video to results\compare\
bat\compare_v3_v4 --source clip.mp4
bat\compare_photos            # same, for the pictures in the test_photos folder

# phone as the camera: install "IP Webcam" (Android), start the server, use the URL it shows
python scripts/07_detect_stream.py --source http://PHONE_IP:8080/video --show

# recorded clip, publishing to a public test MQTT broker
python scripts/07_detect_stream.py --source data/videos/campus-gate_2026-11-18_am.mp4 --mqtt-host test.mosquitto.org
```

Set `--conf` to the `best_conf` value from the evaluation table. Records are appended to
`results/events.jsonl` and published to `bantayaso/<device-id>/events`; a heartbeat goes to
`bantayaso/<device-id>/status`. Before training is done you can try it with the
COCO-pretrained model: `--weights yolo26n.pt`.

## 8. Export for devices

```powershell
python scripts/06_export.py                      # NCNN for Raspberry Pi 5, ONNX for laptops
python scripts/06_export.py --formats tflite     # Android
```

## License note

Ultralytics YOLO is licensed under AGPL-3.0. That is fine for this school project as long as
the code stays open. Selling BantayAso as a closed-source service would need an Ultralytics
Enterprise License.

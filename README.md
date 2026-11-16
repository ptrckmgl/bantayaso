# BantayAso: Python API + monitoring dashboard

This repository now includes a local LGU monitoring prototype alongside the existing machine learning scripts. The dashboard is a React interface, while **Python handles device events, snapshots, validation, storage, analytics, and simulation**. The prototype does not run AI detection or require CCTV hardware.

```text
Python IoT simulator ──multipart image + metadata──> FastAPI ──> SQLite + snapshot files
                                                     │
                                                     └──JSON API──> React dashboard
```

## Run the dashboard locally

Use Python 3.11 or newer and Node.js 20 or newer. From the repository root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open **http://localhost:5173**. The Python API is at **http://127.0.0.1:8000/docs**. Vite proxies `/api` and `/snapshots` to FastAPI. On other shells, use `npm` instead of `npm.cmd` and activate the virtual environment as appropriate.

Keep both terminals open while using the dashboard. If a review action says the local API is unavailable, restart the Python backend command in the first terminal, then retry. The dashboard cannot save a review change while FastAPI is stopped.

The first API startup creates `backend/straywatch.db` with **one example location and camera** (`CAM-001` at Town Plaza). It starts with **zero detections and zero snapshots**. The dashboard explains the camera → API → storage → review flow and refreshes every 15 seconds. Click **Generate one example event** to create a single Python generated snapshot and detection record, or send one through the device ingestion endpoint with the IoT simulator:

```powershell
.venv\Scripts\python.exe -m iot.simulator --device CAM-001 --dogs 2
```

The simulator requires the API to be running. Change `--device` to any registered camera ID, or use **Generate example event for this camera** on a camera card. It uses Pillow to draw a clearly labeled **still frame**, with no camera or model needed. Simulated events do not mark a physical camera as online. A real camera integration can later use OpenCV and the existing `scripts/07_detect_stream.py` pipeline, then POST its validated count and encoded frame to `/api/detections`.

### Dashboard features

- API-backed totals, seven day trends, monitoring zone map, and recent captures after events arrive.
- Searchable, filterable detection history with review, flag, individual delete, clear all, details, and CSV export.
- CCTV device list and registration, with connectivity state and a choice of an existing or newly created monitoring zone.
- Analytics by day and monitoring zone.
- Responsive layout and persistent light/dark mode.

### API and storage

FastAPI routes include `/api/dashboard/summary`, `/api/devices`, `/api/devices/{device_id}`, `/api/detections`, `/api/detections/{detection_id}`, `/api/locations`, `/api/analytics`, and `/api/demo/simulate`. Camera registration accepts an existing `location_id` or a `new_location` object containing a zone name, barangay, and optional description; both camera and new zone are saved together. `POST /api/locations` can also register a zone by itself. The prototype map places new zones approximately until real coordinates are available. `POST /api/detections` accepts `multipart/form-data` fields `device_id`, `timestamp` (ISO 8601), `dog_count`, `confidence`, `source`, and optional `snapshot` (PNG, JPEG, or WebP; maximum 5 MB). Detection and device records are stored with SQLAlchemy in SQLite, with `DATABASE_URL` available to point at PostgreSQL later. Snapshot file references are stored in the database and served from `/snapshots/`. Review status is updated with `PATCH /api/detections/{detection_id}`. `DELETE /api/detections/{detection_id}` removes one **Reviewed** record, and `DELETE /api/detections` clears all records **only when every record is Reviewed**. Both remove snapshots no longer referenced by a record. Pending and Flagged records return HTTP 409 if deletion is attempted through the API.

The demo does not authenticate operators or devices, and its illustrations are placeholders rather than camera footage. Add authentication, device credentials, migration tooling, and actual image inference before real deployment.

## Existing ML work

The machine learning part of **BantayAso**, an IoT system that helps barangays monitor stray dogs.
A YOLO26n object detector finds `dog` and `person` in camera frames, a tracker turns detections
into sightings, and a simple rule marks dogs with no person nearby as **unaccompanied** (our
working definition of a likely stray). Each sighting becomes a small JSON record sent to the
dashboard over MQTT.

```
camera / phone / CCTV  ->  edge node (07_detect_stream.py)  ->  MQTT  ->  cloud + dashboard
                           YOLO26n + ByteTrack + "unaccompanied" rule
```

COSC 105 (Intelligent Systems) component, Cavite State University, BSCS 4-1 Group 4.

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
| `scripts/07_detect_stream.py` | The edge node: live detection, tracking, sighting records, MQTT |
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

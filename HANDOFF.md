# Handoff: BantayAso ML (for Claude Code)

Paste this into Claude Code from inside the unzipped `bantayaso` folder.

## Who and what

I'm Pat, a BSCS 4-1 student at Cavite State University (Indang, Cavite). My group (7 people) is building
**BantayAso**, an IoT system that helps barangays monitor stray dogs. I own the **COSC 105 Intelligent
Systems** part: a trained supervised ML model plus the dataset/ML documentation. Groupmates own the
IoT prototype, the HCI dashboard, and the research paper.

- **Paper deadline: 2026-11-20.** ML results (test set numbers, confusion matrix, comparison table) must be
  final by **2026-11-17** so they can go into the paper.
- **Final presentation and live demo: 2026-11-27.**
- The IoT prototype is **digital only** (no physical Raspberry Pi). For the demo, a phone is the camera
  (IP Webcam app streaming to my laptop, or the model running on the phone), and we test live on stray
  dogs on campus.
- My machine: Windows with an **NVIDIA RTX 4060 (8 GB)**. Train locally; Colab/Kaggle only as backup.

## Decisions already made (don't re-litigate unless something breaks)

- **Model: YOLO26n** (Ultralytics, Jan 2026, latest released; YOLO27 has no weights yet), 640 px.
  Export NCNN for Raspberry Pi 5 / ONNX for laptop / TFLite for Android.
  The panel asked "why not the latest YOLO?" -> we use the latest, and prove it by training
  **YOLOv5n (yolov5nu.pt), YOLO11n and YOLO26n with identical settings** and comparing them on our test set.
- **Classes: `dog` (0) and `person` (1).** A camera can't see ownership, so "stray" is defined as an
  **unaccompanied dog**: ByteTrack track with a person near it in < 30% of its frames
  (near = person centre within 2 x dog-box diagonal).
- **Data:** public first (Open Images V7 + COCO 2017 dog/person subsets via FiftyOne, plus licensed
  Roboflow Universe stray dog sets), then our own phone footage of campus/street dogs.
  Own footage is the **real-world test set**, split **by clip** (never by frame). Report two results:
  public test split and own-footage test; discuss the gap.
- **Metrics:** precision, recall, F1, mAP@0.5, mAP@0.5:0.95, confusion matrix, per-condition recall
  (day/night/rain). Proposed targets: P >= 0.90, R >= 0.85, F1 >= 0.87, mAP50 >= 0.85 (our proposal, not a
  standard). System tests: count MAE per clip, event precision/recall, duplicate-count rate, FPS,
  end-to-end latency, offline buffering.
- **License:** Ultralytics is AGPL-3.0 -> fine if the code is open; a closed commercial service needs an
  Enterprise License.
- The course guide (section D) requires these ML doc headings: problem definition, dataset (source,
  samples, features, target, collection), data preparation (cleaning, missing/invalid values,
  transformation, feature engineering, split), model selection (+ alternatives), training (procedure,
  parameters, tools), evaluation (metrics, results, confusion matrix, interpretation, limitations),
  integration (how input reaches the model, how output reaches the user). Data preparation is also
  graded for IoT.

## Repo state

See README.md for the full layout and commands. Pipeline:
`01_download_public.py` -> `02_download_roboflow.py` -> (`extract_frames.py` for own videos, label in
Roboflow, export YOLOv8 into `data/raw/own/`) -> `03_merge_datasets.py` -> `04_train.py` ->
`05_evaluate.py` -> `06_export.py` -> `07_detect_stream.py` (edge node: tracking, unaccompanied rule,
JSON sighting records to `results/events.jsonl` and MQTT `bantayaso/<device>/events`).
`docs/dataset_documentation.md` is the write-up template (TODOs to fill from `results/`).

**Tested:** `03_merge_datasets.py` and `extract_frames.py` on dummy data; all scripts compile.
**NOT tested** (written without PyTorch/GPU available): `01_download_public.py` (FiftyOne API),
`02_download_roboflow.py`, `04_train.py`, `05_evaluate.py` (Ultralytics metric attributes such as
`box.mp`, `box.mr`, `box.p`, `box.ap_class_index`, `box.f1_curve`), `06_export.py`,
`07_detect_stream.py` (`model.track(..., stream=True)`, paho-mqtt v2 client).
Expect small API fixes in those.

## What I need from you (Claude Code), in order

1. Help me set up the venv with CUDA PyTorch and confirm `torch.cuda.is_available()` is True.
2. Run `01_download_public.py --max-samples 200` and fix any FiftyOne issues; then the full download.
3. Before each Roboflow set: check its page for license and latest version and update
   `configs/sources.yaml`. Then run `02_download_roboflow.py` (my key is in the `ROBOFLOW_API_KEY` env var).
4. `03_merge_datasets.py`; show me `results/dataset_stats.csv` and `results/cleaning_log.csv`.
5. Smoke test: `04_train.py --epochs 3 --fraction 0.1 --models yolo26n.pt`, then `05_evaluate.py`;
   fix anything that breaks. Then the full three-model training (can run overnight).
6. Try `07_detect_stream.py --weights yolo26n.pt --source 0 --show` (pretrained COCO model) to check the
   live path before my trained model exists.
7. Once the GitHub repo exists, push there (`.gitignore` already excludes data, runs and weights).

Keep changes small and explain them; I have to defend this code in front of a panel.

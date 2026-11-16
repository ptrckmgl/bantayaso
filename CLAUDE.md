# BantayAso ML repo: notes for AI coding assistants

- Final model: `models/yolo26n_v4.pt` (YOLO26n, classes `dog`, `person`). Backup: `models/yolo26n_v3.pt`.
- To run the detector or connect it to the dashboard (MQTT, JSON sighting records), follow
  `docs/RUN_AND_INTEGRATE.md`. The detector is `scripts/07_detect_stream.py`; always pass
  `--weights models/yolo26n_v4.pt`.
- The dashboard consumes sighting records published on `bantayaso/<device-id>/events`. It does not
  need the model or raw boxes.
- Training and dataset details: `README.md` and `docs/dataset_documentation.md`. Do not retrain
  or change the dataset unless asked. `data/`, `runs/` and datasets are not in git.
- Windows project: use PowerShell syntax, `.venv\Scripts\python.exe`, and install PyTorch with CUDA
  before `pip install -r requirements.txt`.

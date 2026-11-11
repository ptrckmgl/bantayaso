# StrayWatch: Machine Learning and Dataset Documentation

Follows section D of the course guide (COSC 105). Replace every `TODO` with real values;
most numbers come from the files in `results/`.

## 1. Problem definition

StrayWatch uses supervised object detection. Given a camera frame, the model finds and boxes
every `dog` and `person`. A tracker (ByteTrack) links detections across frames so each dog that
passes the camera is one **sighting**. A rule marks a sighting **unaccompanied** when no person
is near the dog in at least 70% of its frames. Since a camera cannot see ownership, the system
reports unaccompanied dogs as its stand-in for strays.

## 2. Dataset

### 2.1 Sources and licenses

| Source | Images used | License | Link |
| --- | --- | --- | --- |
| Open Images V7 (Dog, Person) | TODO | Annotations CC BY 4.0; images CC BY 2.0 | https://storage.googleapis.com/openimages/web/index.html |
| COCO 2017 (dog) | TODO | Annotations CC BY 4.0; images under Flickr licenses | https://cocodataset.org |
| Roboflow: TODO | TODO | TODO | TODO |
| Own footage (Indang, Cavite) | TODO | Ours | n/a |

### 2.2 Number of samples (from `results/dataset_stats.csv`)

| Split | Images | Empty images | Dog boxes | Person boxes |
| --- | --- | --- | --- | --- |
| train | TODO | TODO | TODO | TODO |
| val | TODO | TODO | TODO | TODO |
| test_public | TODO | TODO | TODO | TODO |
| test (own footage) | TODO | TODO | TODO | TODO |

### 2.3 Features and target

- **Features:** the RGB pixels of each image, resized to 640 x 640. The convolutional network
  learns its own features from them; no hand-made features are used.
- **Target:** for every object, a class label (`dog` = 0, `person` = 1) and a bounding box
  (centre x, centre y, width, height, scaled 0 to 1).

### 2.4 Data collection

- Public data: downloaded on TODO (date) with `scripts/01_download_public.py` and
  `scripts/02_download_roboflow.py`; settings in `configs/sources.yaml`.
- Own footage: TODO number of clips filmed at TODO places on TODO dates, with a TODO (phone
  model), held about 2.5 to 3 m high. Frames taken at 1 per second (`scripts/extract_frames.py`).
- Conditions covered: TODO (day / dusk / night / rain counts).
- Labeling: Roboflow, auto-labeled with the pretrained model and corrected by hand by TODO.
  TODO% of frames re-checked by a second member; agreement: TODO.

## 3. Data preparation

From `results/cleaning_log.csv`:

| Step | What was done | Count |
| --- | --- | --- |
| Class mapping | Source classes mapped to `dog` / `person`; others dropped | TODO |
| Duplicates | Exact duplicate images removed (file hash) | TODO |
| Unreadable images | Removed | TODO |
| Blurry images | Flagged (Laplacian variance < 60) / dropped | TODO |
| Invalid boxes | Clipped to the image; tiny or empty boxes dropped | TODO |
| Polygons | Segmentation labels converted to boxes | TODO |
| Missing labels | Images without a label file kept as negatives (no objects) | TODO |

- **Transformation:** images resized/letterboxed to 640 px; all sources converted to YOLO format.
- **Augmentation (training only):** Ultralytics defaults: mosaic, random flips, HSV colour
  jitter, scaling and translation. TODO: add anything changed.
- **Split:** public data 75/15/10 by image; own footage by clip, so no clip appears in two
  splits. Seed 42.

## 4. Model selection

**Selected:** YOLO26n (Ultralytics, January 2026). TODO: summarise the reasons (newest model,
built for CPU/edge use, NMS-free, 40.9 COCO mAP50-95 at 2.4 M parameters).

| Alternative | Why not chosen |
| --- | --- |
| YOLOv5n | About 13 points lower COCO mAP at a similar size |
| YOLO11n | Close in accuracy; kept as a comparison |
| SSD-MobileNet | Light, but clearly less accurate on small, far objects |
| Faster R-CNN | Accurate, but far too slow for an edge device |

## 5. Model training

- Hardware: NVIDIA RTX 4060 (8 GB), TODO CPU/RAM. Software: Python TODO, PyTorch TODO,
  Ultralytics TODO.
- Settings (`results/training_settings.json`): COCO-pretrained weights, 640 px, up to 100
  epochs, early stopping after 20 epochs without improvement, automatic batch size, seed 42,
  default optimizer and learning rate.
- Training time per model: TODO. Figures: loss and mAP curves from `runs/train/<model>/results.png`.

## 6. Model evaluation

### 6.1 Comparison on the test set (`results/comparison_test.md`)

TODO: paste the table (precision, recall, F1, mAP50, mAP50-95, inference ms).

### 6.2 Public test vs real-world test

TODO: compare `comparison_public.md` with `comparison_test.md` and explain the gap.

### 6.3 Confusion matrix and curves

TODO: insert `runs/eval/yolo26n_test/confusion_matrix_normalized.png`, `PR_curve.png`,
`F1_curve.png`, and explain what each shows.

### 6.4 Error analysis

TODO: 4 to 6 example images of misses and false alarms (night, far dogs, cats, hidden dogs)
and why each happened.

### 6.5 Limitations

- TODO: one town, few night or rain frames, mostly aspins.
- "Unaccompanied" is a stand-in for "stray"; owned dogs roaming alone are counted too.
- Tested on recorded and live phone video, not on a deployed outdoor device.

## 7. Integration

Camera (phone or CCTV stream) -> edge node (`scripts/07_detect_stream.py`: YOLO26n + ByteTrack +
unaccompanied rule) -> JSON sighting record over MQTT (`straywatch/<device>/events`) ->
cloud database -> dashboard. TODO: paste one real record and a screenshot of the dashboard
entry it created.

## 8. Ethics and privacy

TODO: faces and plates blurred before sharing; only records, not video, leave the device;
Data Privacy Act (RA 10173).

## 9. Maintenance

TODO: where the data is stored, dataset version, how to add a new site.

# BantayAso: Machine Learning and Dataset Documentation

Follows section D of the course guide (COSC 105). Replace every `TODO` with real values;
most numbers come from the files in `results/`.

## 1. Problem definition

BantayAso uses supervised object detection. Given a camera frame, the model finds and boxes
every `dog` and `person`. A tracker (ByteTrack) links detections across frames so each dog that
passes the camera is one **sighting**. A rule marks a sighting **unaccompanied** when no person
is near the dog in at least 70% of its frames. Since a camera cannot see ownership, the system
reports unaccompanied dogs as its stand-in for strays.

### 1.1 What the system calls a "stray"

Whether a dog is a stray depends on ownership, and ownership is not visible in an image. A
collar is too small to see from a mounted camera, a person near a dog may not be its owner,
and many owned dogs roam the street alone. So BantayAso does **not** claim to identify
strays. It reports **unaccompanied dog sightings** with supporting evidence, and barangay staff
make the decision (human in the loop).

| Term | Definition | Where it is computed |
|---|---|---|
| Sighting | One tracked dog (one ByteTrack ID) from when it appears until it is unseen for 5 s; tracks shorter than 3 processed frames are ignored as noise. | Edge node |
| Near | A person box whose centre is within 2 x the dog box's diagonal of the dog box's centre (scales with distance from the camera). | Edge node |
| Unaccompanied | A person is near the dog in fewer than 30% of the sighting's frames (`accompanied_ratio < 0.3`). | Edge node |
| Evidence fields | `duration_s` (passing by vs lingering), `max_dogs_in_view` (dogs in a group), `night` (sighting started 18:00-06:00), `max_conf` (detector confidence). Recorded, **not** combined into a score, because we have no data to set weights. | Edge node |
| Hotspot | A camera/location with unaccompanied sightings on several different days. Built from the records; the system does not recognise individual dogs, so this describes a place, not a dog. | Dashboard |

The 2 x diagonal and 30% thresholds are our proposal. TODO: check them on our own labelled
clips (count how often walked dogs are marked unaccompanied, and loose dogs marked
accompanied) and adjust with `--near-k` and `--accompanied-ratio`.

Why "unaccompanied" is still the useful category: dogs roaming public places without a person
are the ones local rules on rabies control and impounding are concerned with, whether or not
they have an owner. TODO: cite the exact section of the Anti-Rabies Act of 2007 (RA 9482) and
the barangay or municipal ordinance after checking their wording.

## 2. Dataset

### 2.1 Sources and licenses

| Source | Images used | License | Link |
| --- | --- | --- | --- |
| Open Images V7 (Dog, Person) | 2,996 (3,000 downloaded) | Annotations CC BY 4.0; images CC BY 2.0 | https://storage.googleapis.com/openimages/web/index.html |
| COCO 2017 (dog) | 2,495 (2,500 downloaded) | Annotations CC BY 4.0; images under Flickr licenses | https://cocodataset.org |
| Roboflow: senox-xmqbj / stray-dog-detection-5klnz v3 (CCTV, dog and person) | 6,392 (9,484 downloaded) | CC BY 4.0 | https://universe.roboflow.com/senox-xmqbj/stray-dog-detection-5klnz/dataset/3 |
| Roboflow: lr3 / stray-dogs-dsns7 v3 (dog and person) | 2,061 (3,469 downloaded) | CC BY 4.0 | https://universe.roboflow.com/lr3/stray-dogs-dsns7/dataset/3 |
| Cat photos as hard negatives (no dog, empty labels) | 1,499 (1,500 downloaded) | see `scripts/download_cat_negatives.py` and `results/v3/download_cat_negatives.log` | n/a |
| Own footage | none yet (TODO) | Ours | n/a |

"Downloaded" is the number of images fetched; "used" is what remained in the final training set
after cleaning (section 3). The Roboflow sets are CC BY 4.0, so the authors must be credited
in the paper.

### 2.2 Number of samples (from `results/dataset_stats.csv`, model v4)

| Split | Images | Empty images | Dog boxes | Person boxes |
| --- | --- | --- | --- | --- |
| train | 11,586 | 1,529 | 12,116 | 33,233 |
| val | 2,315 | 314 | 2,562 | 6,333 |
| test_public | 1,542 | 225 | 1,817 | 3,989 |
| test (own footage) | TODO | TODO | TODO | TODO |

Total 15,443 images. The previous dataset version used for model v3 (18,882 images, split by
image) is kept in `data/merged_v3`; the one used for v2 in `data/merged_v2`.

### 2.3 Features and target

- **Features:** the RGB pixels of each image, resized to 640 x 640. The convolutional network
  learns its own features from them; no hand-made features are used.
- **Target:** for every object, a class label (`dog` = 0, `person` = 1) and a bounding box
  (centre x, centre y, width, height, scaled 0 to 1).

### 2.4 Data collection

- Public data: Open Images and COCO downloaded with `scripts/01_download_public.py` (FiftyOne),
  the two Roboflow sets exported from Roboflow Universe in YOLO format (November 2026), and the
  cat negatives with `scripts/download_cat_negatives.py`; settings in `configs/sources.yaml`.
- The lr3 set had many people without a box. A stock COCO-pretrained `yolo26n.pt` was used to
  add the missing `person` boxes (person class only, confidence >= 0.6, only where no existing
  person label overlapped with IoU >= 0.5; dog labels untouched): 1,038 boxes added to 683 of
  3,469 images (`scripts/pseudo_label_persons.py`, log in `results/pseudo_label_persons_log.txt`).
  These are model-made labels, not human labels, and are a source of label noise.
- Own footage: TODO number of clips filmed at TODO places on TODO dates, with a TODO (phone
  model), held about 2.5 to 3 m high. Frames taken at 1 per second (`scripts/extract_frames.py`).
- Conditions covered: TODO (day / dusk / night / rain counts).
- Labeling: Roboflow, auto-labeled with the pretrained model and corrected by hand by TODO.
  TODO% of frames re-checked by a second member; agreement: TODO.

## 3. Data preparation

From `results/cleaning_log.csv`:

| Step | What was done | Count |
| --- | --- | --- |
| Class mapping | Source classes mapped to `dog` / `person`; others dropped (lr3's unused class 0) | 2 boxes dropped |
| Exact duplicates | Byte-identical images removed (MD5 hash) | 1 image |
| Unreadable images | Removed | 5 images |
| Cross-dataset near-duplicates | Image dropped if almost identical (dHash within 6 of 64 bits) to one already kept from another source (975 lr3 images were re-uploads of senox images) | 1,065 images |
| Repeated video frames | Within one camera/video, a frame is dropped only if an earlier kept frame is within 10 dHash bits **and** has the same number of dog and person boxes; frames showing anything new are kept | 3,439 images |
| Blurry images | Flagged (Laplacian variance < 60), kept | 343 images |
| Invalid boxes | Clipped to the image / tiny or empty boxes dropped | 704 clipped / 3 dropped |
| Polygons | Segmentation labels converted to boxes | none present |
| Missing labels | Images without boxes kept as negatives (1,499 cat photos plus others) | 2,068 empty images in all splits |

- **Transformation:** images resized/letterboxed to 640 px; all sources converted to YOLO format.
- **Augmentation (training only):** Ultralytics defaults: mosaic, random flips, HSV colour
  jitter, scaling and translation (details in 5.1). No change from the defaults.
- **Split (leakage-free):** public data 75/15/10 into train/val/test, split by **group**, not by
  image. A group is all copies of one original Roboflow image, all near-duplicates, and all
  frames of one camera or video (identified from the camera/video id in the file name, 310
  cameras/videos, `--split-by-scene`), so no camera or video has frames in two splits (checked: 0
  of 450 identifiable CCTV test images share a camera with training). Own footage, when added,
  is split by clip. Seed 42.
- **Why the leakage fix matters:** an earlier split by image only (model v3) had 843 of 879
  identifiable CCTV test images from cameras also seen in training, which inflates scores.
  Model v2 showed the effect: mAP50 0.83 on images it had partly trained on versus 0.76 on
  unseen ones.
- **Not clustering:** the grouping above uses fixed rules (a perceptual hash and file-name ids);
  nothing is learned. The detector itself is supervised learning.

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

- Hardware: NVIDIA RTX 4060 Laptop GPU (8 GB), Intel Core i7-12650H, 16 GB RAM.
  Software: Python 3.14.7, PyTorch 2.14.1 (CUDA 13.0), Ultralytics 8.4.210.
- Procedure: each model starts from its COCO-pretrained weights (transfer learning) and is
  fine-tuned on `train`; after every epoch it is scored on `val`, and the epoch with the best
  val mAP@0.5:0.95 is kept as `best.pt`. The test sets are used only once, after training.
- Training time: v4 (final model) 50 epochs in 1.78 h (6,411 s); v3 2.14 h. Figures: loss and
  mAP curves from `runs/train/yolo26n_v4/results.png`.
- Model versions: v1 (COCO and Open Images only), v2 (two Roboflow CCTV sets), v3 (all sources,
  split by image), **v4 (final: all sources, leakage-free split by camera/video, repeated
  frames thinned)**. v1 to v3 are kept in `runs/train/` and their data in `data/merged_v*` for
  the comparison.

### 5.1 Training settings and why

YOLOv5n (`yolov5nu.pt`), YOLO11n and YOLO26n are trained with exactly the same settings
(`scripts/04_train.py`, saved to `results/training_settings.json`), so differences in the
results come from the architectures, not from tuning. Every value is either fixed by us or an
Ultralytics default; nothing is chosen automatically per model. (Only YOLO26n has been trained
on the final v4 data so far; the YOLOv5n / YOLO11n comparison runs are still to do.)
Command for v4: `python scripts/04_train.py --models yolo26n.pt --tag v4 --epochs 50
--patience 10 --batch 16 --workers 4`. Not used, on purpose: `batch=-1` (batch 32 ran out of
memory on the ~4 GB of GPU memory usable on this laptop), `cache="ram"` (16 GB RAM) and
`compile=True` (slower first epoch, less stable on Windows).

| Setting | Value | Justification |
|---|---|---|
| Initial weights | COCO-pretrained | COCO already contains `dog` and `person`; fine-tuning pretrained weights needs far less data than training from scratch (v4 has 11,586 training images). |
| Image size | 640 px | The size the pretrained weights were trained at, and the input size used when deployed. |
| Epochs | 50 (v1 used 100) | Deadline-driven and checked: v1's val mAP50 at epoch 50 was 0.757, about 98% of its best (0.775 at epoch 80); v3's val mAP50 was 0.759 at epoch 40 and 0.761 at epoch 50, so the curve had flattened. |
| Early stopping | patience 10 | Stops when val fitness (Ultralytics: 0.1 x mAP50 + 0.9 x mAP50-95) has not improved for 10 epochs; limits overfitting and saves time. (v4 ran all 50 epochs; the best checkpoint is epoch 50: val mAP50 0.698, mAP50-95 0.442, precision 0.785, recall 0.612. The highest val mAP50 alone, 0.699, was at epoch 38.) |
| Batch size | 16 (fixed) | Ultralytics default, and fits all three nano models in 8 GB. Fixed instead of AutoBatch so all models get the same value. Gradients are accumulated to a nominal batch of 64 (`nbs=64`), so the effective batch is 64 for every model. |
| Optimizer | AdamW, lr0 = 0.00167, beta1 = 0.9 | Written out explicitly but identical to what Ultralytics' `optimizer=auto` selects for short fine-tuning runs (< 10,000 optimizer steps; v4 is ceil(11586 / 64) x 50 = 9,100): AdamW with lr0 = 0.002 x 5 / (4 + number of classes) = 0.00167. SGD with lr0 = 0.01 is the default for long from-scratch COCO training. |
| LR schedule | linear decay to 1% of lr0, 3 warm-up epochs | Ultralytics defaults; warm-up avoids destroying pretrained weights with large early updates. |
| Weight decay | 0.0005 | Ultralytics default (L2 regularisation against overfitting). |
| Augmentation | mosaic (off for the last 10 epochs), horizontal flip 0.5, scale +/-50%, translate +/-10%, HSV jitter (hue 0.015, saturation 0.7, brightness 0.4); no vertical flip, mixup or cutmix | Ultralytics defaults. They match our conditions: brightness/colour jitter for day, dusk and night lighting; scale for dogs near and far from the camera; horizontal flip because dogs walk both ways; no vertical flip because a mounted camera is never upside down. |
| Mixed precision | on (AMP) | Faster training and lower memory on the GPU, with no measurable accuracy loss. |
| Seed | 42, deterministic | Makes the runs repeatable. |

## 6. Model evaluation

### 6.1 Results of the final model v4 on the public test split (`results/v4/v4_report.md`)

Test split: 1,542 images, no camera or video shared with training. Confidence 0.35 (F1-optimal).

| Test images | Precision | Recall | F1 | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| All (1,542) | 0.764 | 0.633 | 0.692 | 0.704 | 0.448 |
| CCTV only (845) | 0.759 | 0.622 | 0.684 | 0.702 | 0.433 |
| COCO + Open Images (548) | 0.775 | 0.668 | 0.717 | 0.728 | 0.486 |

Per class (all): dog P 0.815, R 0.737, AP50 0.805; person P 0.712, R 0.529, AP50 0.603.
Cat photos (149, hard negatives): 7 images get a false dog at confidence 0.35.
Inference time on the RTX 4060 laptop GPU: about 1.4 ms per image (Ultralytics speed line).
TODO: inference ms on the edge device (Raspberry Pi) after export.

### 6.2 Model versions and the effect of data leakage

| Model | Data | Test set | mAP50 | Note |
|---|---|---|---|---|
| v1 | COCO + Open Images | v1 own test | 0.772 | easy, one domain |
| v1 | same | CCTV test of v2 | 0.163 | domain shift |
| v2 | two CCTV sets | v2 test | 0.730 | split by image: test shared cameras with training |
| v3 | all sources | v3 test | 0.736 | split by image: 843 of 879 identifiable CCTV test images shared a camera with training |
| **v4** | all sources, thinned | **v4 test** | **0.704** | split by camera/video: 0 of 450 shared; the honest figure |

Same-image comparison on 962 test images that v1 and v2 never trained on (mAP50): v3 0.734,
v1 0.622, v2 0.497. On COCO and Open Images only, v4 (0.728) and v3 (0.720) tie, and v4 makes
fewer cat false alarms (7 vs 12 of 149; v2: 103). v3 scores higher than v4 on CCTV images from
cameras it trained on (0.80 vs 0.70); this is largely familiarity with those cameras, so only
v4's number measures how the model does on a new camera.
The own-footage (real-world) test is still to do (TODO), and will be the gap to discuss against
the public test.

### 6.3 Confusion matrix and curves

Validation-split plots of the v4 run (the test split was scored without plots): in
`runs/train/yolo26n_v4/`: `confusion_matrix_normalized.png`, `BoxPR_curve.png`,
`BoxF1_curve.png`, `BoxP_curve.png`, `BoxR_curve.png`, `results.png` (loss and metric curves).
Confidence trade-off for v4 on its test split (mean of dog and person): conf 0.50 gives P 0.88 / R 0.52, 0.35 gives P 0.80 / R 0.61 (best F1, 0.690), 0.25 gives P 0.72 / R 0.66, 0.15 gives P 0.61 / R 0.71, 0.10 gives P 0.53 / R 0.75. For v3 it was: conf 0.50 gives
P 0.88 / R 0.59, 0.35 gives 0.80 / 0.67 (best F1), 0.25 gives 0.72 / 0.71, 0.15 gives 0.60 / 0.75.
TODO: describe each figure after looking at it (what the diagonal of the confusion matrix
shows, where the F1 curve peaks, why person recall is lower than dog recall).

### 6.4 Error analysis

TODO: 4 to 6 example images of misses and false alarms (night, far dogs, cats, hidden dogs)
and why each happened.

### 6.5 Limitations

- Test numbers are from public and CCTV-style images; no own-footage test yet (TODO). Targets
  in earlier drafts (P >= 0.90, R >= 0.85, F1 >= 0.87, mAP50 >= 0.85) were a first guess made
  before any training; realistic targets for this nano model are mAP50 >= 0.70 and
  precision/recall/F1 around 0.70 to 0.80, which v4 meets for mAP50 and F1-level precision, but
  not for recall (0.63).
- Person recall (0.53) is the weakest number: people are small and far in CCTV frames, the
  person labels differ between sources, and the lr3 set had unlabeled people that were only
  partly fixed by pseudo-labeling (1,038 boxes, confidence >= 0.6).
- Many CCTV images are consecutive frames of a few hundred cameras/videos (310), so the CCTV
  part has less variety than its image count suggests. v1 to v3 were scored on tests that
  shared cameras with training (section 6.2).
- Nano model at 640 px: small, distant dogs and people are missed. A larger model (YOLO26s)
  would help but is too heavy for the low-end IoT device.
- Only one training run per model (seed 42); small differences between models (about 0.01
  mAP50) are within noise.
- One town expected for the own footage, few night or rain frames, mostly aspins (TODO: confirm
  after filming).
- "Unaccompanied" is a stand-in for "stray" (section 1.1): owned dogs roaming alone are
  counted too, and a stray near a passer-by, vendor or feeder is counted as accompanied.
- The system cannot recognise an individual dog, so the same dog passing twice is two
  sightings, and repeat sightings describe a place, not a dog.
- `night` uses the clock (or `--video-start` for recorded clips), not the image brightness.
- Tested on recorded and live phone video, not on a deployed outdoor device.

## 7. Integration

Camera (phone or CCTV stream) -> edge node (`scripts/07_detect_stream.py`: YOLO26n + ByteTrack +
unaccompanied rule) -> JSON sighting record over MQTT (`bantayaso/<device>/events`) ->
cloud database -> dashboard. TODO: paste one real record and a screenshot of the dashboard
entry it created.

## 8. Ethics and privacy

TODO: faces and plates blurred before sharing; only records, not video, leave the device;
Data Privacy Act (RA 10173).

## 9. Maintenance

TODO: where the data is stored, dataset version, how to add a new site.

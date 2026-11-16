# v3 training: overall findings (2026-11-16)

## What v3 is
- YOLO26n trained from the stock COCO-pretrained `yolo26n.pt` (not from v2), 50 epochs, batch 16, imgsz 640, AdamW, patience 10, workers 4.
- Data (`data/merged`): 14,281 train / 2,716 val / 1,885 test_public images. Sources: two Roboflow CCTV sets (CC BY 4.0), COCO 2017 (2,500), Open Images V7 (3,000), 1,500 cat images as empty-label hard negatives.
- lr3 ("stray dogs") had many unlabeled people: 1,038 person boxes added to 683 of its 3,469 images by stock `yolo26n.pt` (person only, conf >= 0.6, no overlap with existing person labels; dog labels untouched). Originals kept in `data/orig_backup`; v2's data in `data/merged_v2`.
- Best validation result: mAP50 0.761, mAP50-95 0.500 (epoch 50).

## Result 1: v3 on its full held-out test split (1,885 images, v3 never trained on any)
| P | R | F1 | mAP50 | mAP50-95 |
|---|---|---|---|---|
| 0.800 | 0.665 | 0.726 | 0.736 | 0.475 |

Per class: dog P 0.797 / R 0.733 / AP50 0.777; person P 0.803 / R 0.598 / AP50 0.696.

## Result 2: fair comparison on images v1 and v2 did not train on (962 images)
These are the 265 CCTV test images not in v2's training set, plus all COCO/Open Images and cat test images.

| Model | P | R | F1 | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| v3 | 0.799 | 0.655 | 0.720 | 0.734 | 0.481 |
| v2 | 0.624 | 0.490 | 0.549 | 0.497 | 0.290 |
| v1 | 0.749 | 0.613 | 0.674 | 0.622 | 0.457 |

By source (mAP50): CCTV-only unseen images (265): v3 0.755, v2 0.760 (tie). COCO + Open Images (548): v3 0.720, v2 0.400.

Cat negatives (149 cat images, conf 0.35): v3 calls a cat a dog on 12 images, v2 on 103.

## Caveats (state these in the paper)
- The new split differs from v1's and v2's. 923 of the 1,188 CCTV test images were in v2's training set, so the full-CCTV numbers (v3 0.740 vs v2 0.827) are NOT a fair comparison. Use the 265-image subset.
- v1's original data is not on this laptop. v1 may have seen some of the same COCO/Open Images pictures, so its score here could be optimistic.
- lr3 test labels now include pseudo-labeled persons (model-made labels, not human labels).
- 265 CCTV images is a small sample: the v3/v2 CCTV difference is within noise.
- Number of runs: one per model, no seeds repeated.

## Take-away
v1 (close-up only) fails on CCTV; v2 (CCTV only) fails on close-ups and cats; v3 (mixed) matches v2 on CCTV and is far better on close-ups and cats. Recall is still the weak point (0.665 overall, person 0.598), below the proposed targets. Next: YOLOv5n / YOLO11n comparison with identical settings, YOLO26s if recall stays low, live and event-level checks with Pat.

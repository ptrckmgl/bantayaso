# v4: clean-split results (2026-11-16)

## What changed from v3
- Same model and settings as v3 (YOLO26n from COCO-pretrained yolo26n.pt, 50 epochs, patience 10, batch 16, imgsz 640, AdamW, seed 42, workers 4). Trained 1.8 h; best checkpoint is epoch 50 by Ultralytics fitness (val mAP50 0.698, mAP50-95 0.442); highest val mAP50 alone was 0.699 at epoch 38.
- Data: split by camera/video (`--split-by-scene`), and repeated CCTV frames thinned (`--thin-repeats 10`: a frame is dropped only if an earlier frame from the same camera is within 10 dHash bits AND has the same dog and person box counts). 3,439 frames removed (3,006 senox, 433 lr3).
- Result: 11,586 train / 2,315 val / 1,542 test images. 0 of 450 identifiable CCTV test images share a camera or video with train (v3: 843 of 879 did).

## v4 on its clean test split (1,542 images, unseen cameras)
| Set | P | R | F1 | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| All | 0.764 | 0.633 | 0.692 | 0.704 | 0.448 |
| CCTV only (845) | 0.759 | 0.622 | 0.684 | 0.702 | 0.433 |
| COCO + Open Images (548) | 0.775 | 0.668 | 0.717 | 0.728 | 0.486 |

Per class (all): dog P 0.815 / R 0.737 / AP50 0.805; person P 0.712 / R 0.529 / AP50 0.603.

## v4 vs v3 on images neither trained on
| Set | Model | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| COCO + Open Images (548) | v4 | 0.775 | 0.668 | 0.728 | 0.486 |
| COCO + Open Images (548) | v3 | 0.789 | 0.652 | 0.720 | 0.477 |

Cat negatives (149 cat images, conf 0.35): false dog on 7 images with v4, 12 with v3, 103 with v2.

## Caveats
- v3 trained on many images that are in v4's new test split (shared cameras), so v3 cannot be scored fairly on the CCTV part of this test. Only the COCO/OI and cat comparisons are like-for-like.
- v3's earlier CCTV numbers (mAP50 0.74-0.76) were measured on cameras seen in training; v4's 0.70 on unseen cameras is the honest figure.
- Person labels are the weakest part (person AP50 0.60): lr3 had unlabeled people (partly pseudo-labeled) and CCTV persons are small.
- Single run per model, no repeated seeds; v4 vs v3 differences on COCO/OI are within noise.

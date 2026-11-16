"""Add missing `person` boxes to the lr3 'stray dogs' set using stock yolo26n.pt (COCO).

Non-destructive: the source dataset is copied to --out and only the copy's labels are changed.
Only person detections with conf >= --conf are added, and only when they do not overlap an
existing person label (IoU < 0.5). Dog labels are never touched.

    python scripts/pseudo_label_persons.py
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from common import IMAGE_EXTS, RAW

PERSON_ID = 2  # class id of 'person' in the lr3 export (0 unused, 1 dog, 2 person)


def iou(a, b):
    ax1, ay1, ax2, ay2 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1, bx2, by2 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw, ih = max(0, min(ax2, bx2) - max(ax1, bx1)), max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(RAW / "stray dogs.v3i.yolo26"))
    ap.add_argument("--out", default=str(RAW.parent / "pseudo" / "stray dogs.v3i.yolo26"))
    ap.add_argument("--weights", default="yolo26n.pt")
    ap.add_argument("--conf", type=float, default=0.6)
    a = ap.parse_args()
    ds = Path(a.out)
    if not ds.exists():
        shutil.copytree(a.src, ds)
    model = YOLO(a.weights)
    total_added = imgs_changed = n_imgs = 0
    for split in ("train", "valid", "test"):
        img_dir, lab_dir = ds / split / "images", ds / split / "labels"
        files = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        for f in files:
            try:
                r = model.predict(str(f), classes=[0], conf=a.conf, imgsz=640, verbose=False)[0]
            except Exception as e:  # one bad image must not stop the run
                print("skipped", f.name, type(e).__name__)
                continue
            n_imgs += 1
            lf = lab_dir / (Path(r.path).stem + ".txt")
            lines = [l for l in (lf.read_text().splitlines() if lf.exists() else []) if l.strip()]
            existing = [list(map(float, l.split()[1:5])) for l in lines if int(l.split()[0]) == PERSON_ID]
            new = [f"{PERSON_ID} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}"
                   for b in r.boxes.xywhn.tolist() if all(iou(b, e) < 0.5 for e in existing)]
            if new:
                lf.write_text("\n".join(lines + new) + "\n")
                total_added += len(new)
                imgs_changed += 1
    print(f"images scanned: {n_imgs}, images changed: {imgs_changed}, person boxes added: {total_added}")


if __name__ == "__main__":
    main()

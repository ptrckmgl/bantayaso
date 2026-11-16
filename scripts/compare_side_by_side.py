"""Run two models on the SAME frames and show / save them side by side (left = A, right = B).

    python scripts/compare_side_by_side.py --source clip.mp4
    python scripts/compare_side_by_side.py --source 0 --show             laptop webcam
    python scripts/compare_side_by_side.py --source http://PHONE-IP:8080/video --show

Detections only (dog / person boxes with confidence); no tracking or stray logic, so the
difference you see is the model alone. Press q to stop. Output: results/compare/<name>.mp4.
"""
import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from common import IMAGE_EXTS, RESULTS

COLORS = {0: (255, 90, 0), 1: (0, 200, 255)}  # dog = blue-ish, person = yellow-ish (BGR)
NAMES = {0: "dog", 1: "person"}


def draw(frame, result, label):
    out = frame.copy()
    n_dog = n_person = 0
    for c, conf, (x1, y1, x2, y2) in result:
        n_dog += c == 0
        n_person += c == 1
        cv2.rectangle(out, (x1, y1), (x2, y2), COLORS[c], 2)
        cv2.putText(out, f"{NAMES[c]} {conf:.2f}", (x1, max(14, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[c], 2)
    cv2.rectangle(out, (0, 0), (out.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(out, f"{label}   dogs {n_dog}  persons {n_person}", (8, 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="video file, camera index (0) or stream URL")
    ap.add_argument("--a", default="runs/train/yolo26n_v3/weights/best.pt")
    ap.add_argument("--b", default="runs/train/yolo26n_v4/weights/best.pt")
    ap.add_argument("--a-label", default="v3")
    ap.add_argument("--b-label", default="v4")
    ap.add_argument("--conf", type=float, default=0.35, help="dog threshold")
    ap.add_argument("--person-conf", type=float, default=0.20)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--show", action="store_true", help="show a live window (q stops)")
    ap.add_argument("--out", default="", help="output .mp4 (default results/compare/<source name>.mp4)")
    ap.add_argument("--max-seconds", type=float, default=0, help="stop after this many seconds (0 = whole video)")
    args = ap.parse_args()

    models = [YOLO(args.a), YOLO(args.b)]
    labels = [args.a_label, args.b_label]
    low = min(args.conf, args.person_conf)

    def compare(frame):
        """Run both models on one frame -> (side-by-side image, [(dogs, persons) per model])."""
        panels, counts = [], []
        for i, m in enumerate(models):
            r = m.predict(frame, imgsz=args.imgsz, conf=low, classes=[0, 1], verbose=False)[0]
            dets = [(int(b.cls), float(b.conf), tuple(map(int, b.xyxy[0])))
                    for b in r.boxes if float(b.conf) >= (args.conf if int(b.cls) == 0 else args.person_conf)]
            counts.append((sum(d[0] == 0 for d in dets), sum(d[0] == 1 for d in dets)))
            panels.append(draw(frame, dets, labels[i]))
        both = cv2.hconcat(panels)
        if both.shape[1] > 1920:  # keep the file / window a reasonable size
            s = 1920 / both.shape[1]
            both = cv2.resize(both, None, fx=s, fy=s)
        return both, counts

    # photo mode: a folder of pictures, or one picture -> one side-by-side .jpg per picture
    sp = Path(args.source)
    if sp.exists() and (sp.is_dir() or sp.suffix.lower() in IMAGE_EXTS):
        files = sorted(p for p in sp.iterdir() if p.suffix.lower() in IMAGE_EXTS) if sp.is_dir() else [sp]
        out_dir = Path(args.out) if args.out else RESULTS / "compare" / f"{sp.stem}_{labels[0]}_vs_{labels[1]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        tot = [[0, 0], [0, 0]]
        print(f"{'image':40s} {labels[0] + ' dog/person':>16s} {labels[1] + ' dog/person':>16s}")
        for f in files:
            img = cv2.imread(str(f))
            if img is None:
                print(f"{f.name[:40]:40s} (unreadable, skipped)")
                continue
            both, counts = compare(img)
            cv2.imwrite(str(out_dir / f"{f.stem}.jpg"), both)
            for i, (d, p) in enumerate(counts):
                tot[i][0] += d
                tot[i][1] += p
            print(f"{f.name[:40]:40s} {counts[0][0]:>8d} / {counts[0][1]:<5d} {counts[1][0]:>8d} / {counts[1][1]:<5d}")
        print(f"{'TOTAL':40s} {tot[0][0]:>8d} / {tot[0][1]:<5d} {tot[1][0]:>8d} / {tot[1][1]:<5d}")
        print(f"saved {len(files)} comparison picture(s) to: {out_dir}")
        return

    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"cannot open source: {args.source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    if fps != fps or fps < 1 or fps > 120:
        fps = 15
    name = "webcam" if isinstance(src, int) else Path(str(src)).stem or "stream"
    out_path = Path(args.out) if args.out else RESULTS / "compare" / f"{name}_{labels[0]}_vs_{labels[1]}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    start, frames = time.time(), 0
    totals = [[0, 0], [0, 0]]
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            both, counts = compare(frame)
            for i, (d, p) in enumerate(counts):
                totals[i][0] += d
                totals[i][1] += p
            if writer is None:
                h, w = both.shape[:2]
                writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            writer.write(both)
            frames += 1
            if args.show:
                cv2.imshow("left: " + labels[0] + "   right: " + labels[1] + "   (q = stop)", both)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if args.max_seconds and time.time() - start > args.max_seconds:
                break
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()
    print(f"frames: {frames}")
    for lab, (d, p) in zip(labels, totals):
        print(f"{lab}: {d} dog boxes, {p} person boxes in total")
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()

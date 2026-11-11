"""Evaluate every trained model on the test set and write the comparison table for the paper.

    python scripts/05_evaluate.py                                  # test set from data.yaml
    python scripts/05_evaluate.py --data data/merged/data_public_test.yaml --tag public

Writes results/comparison_<tag>.csv and .md with precision, recall, F1, mAP@0.5,
mAP@0.5:0.95 (overall and per class) and inference speed, plus the confusion matrix and
curves in runs/eval/<model>_<tag>/.

Precision and recall are reported at the confidence threshold that maximises F1
(that is how Ultralytics computes them); the threshold is shown in the table so the
same value can be used in the deployed system.
"""
import argparse
import csv

import numpy as np
from ultralytics import YOLO

from common import MERGED, RESULTS, RUNS


def f1(p, r):
    return 2 * p * r / (p + r) if (p + r) else 0.0


def best_conf(metrics):
    """Confidence at which the mean F1 curve peaks."""
    try:
        curve = np.asarray(metrics.box.f1_curve).mean(0)
        return float(np.linspace(0, 1, len(curve))[curve.argmax()])
    except Exception:
        return float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(MERGED / "data.yaml"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--tag", default="test")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="0")
    args = ap.parse_args()

    runs = sorted(p for p in (RUNS / "train").glob("*/weights/best.pt"))
    if not runs:
        raise SystemExit("No trained models in runs/train/*/weights/best.pt - run 04_train.py first.")

    rows = []
    for w in runs:
        name = w.parents[1].name
        print(f"\n=== Evaluating {name} on {args.split} ({args.tag}) ===")
        m = YOLO(str(w)).val(data=args.data, split=args.split, imgsz=args.imgsz, device=args.device,
                             project=str(RUNS / "eval"), name=f"{name}_{args.tag}", exist_ok=True, plots=True)
        b = m.box
        row = {"model": name, "precision": b.mp, "recall": b.mr, "f1": f1(b.mp, b.mr),
               "mAP50": b.map50, "mAP50-95": b.map, "best_conf": best_conf(m),
               "inference_ms": m.speed.get("inference", float("nan"))}
        for i, cls in m.names.items():
            if i in list(b.ap_class_index):
                k = list(b.ap_class_index).index(i)
                p, r = b.p[k], b.r[k]
                row.update({f"{cls}_precision": p, f"{cls}_recall": r, f"{cls}_f1": f1(p, r),
                            f"{cls}_mAP50": b.ap50[k]})
        rows.append(row)

    RESULTS.mkdir(exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(RESULTS / f"comparison_{args.tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    main_cols = ["model", "precision", "recall", "f1", "mAP50", "mAP50-95", "best_conf", "inference_ms"]
    fmt = lambda v: f"{v:.3f}" if isinstance(v, (float, np.floating)) else str(v)
    lines = ["| " + " | ".join(main_cols) + " |", "|" + "---|" * len(main_cols)]
    lines += ["| " + " | ".join(fmt(r.get(c, "")) for c in main_cols) + " |" for r in rows]
    (RESULTS / f"comparison_{args.tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nSaved results/comparison_{args.tag}.csv and .md; plots in runs/eval/")


if __name__ == "__main__":
    main()

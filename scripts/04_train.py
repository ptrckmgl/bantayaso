"""Train the StrayWatch detector, and the comparison models, with identical settings.

    python scripts/04_train.py                          # YOLO26n, YOLOv5n, YOLO11n in a row
    python scripts/04_train.py --models yolo26n.pt      # just the main model
    python scripts/04_train.py --epochs 3 --fraction 0.1   # quick smoke test

Note: "yolov5nu.pt" is Ultralytics' updated YOLOv5n (anchor-free head) that runs in the
same package; say so in the paper when comparing it with the original YOLOv5.

Outputs: runs/train/<model>/ with weights/best.pt, results.csv, confusion_matrix.png,
PR and F1 curves. Pretrained weights download automatically on first use.
"""
import argparse
import json

from ultralytics import YOLO

from common import MERGED, RESULTS, RUNS

DEFAULT_MODELS = ["yolo26n.pt", "yolov5nu.pt", "yolo11n.pt"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--data", default=str(MERGED / "data.yaml"))
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=float, default=-1, help="-1 = largest batch that fits the GPU")
    ap.add_argument("--patience", type=int, default=20, help="stop after N epochs without improvement")
    ap.add_argument("--device", default="0", help="0 = first GPU, 'cpu', or 'mps' on Apple Silicon")
    ap.add_argument("--workers", type=int, default=4, help="lower to 2 or 0 if Windows crashes loading data")
    ap.add_argument("--fraction", type=float, default=1.0, help="train on a fraction of the data (testing)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    batch = int(args.batch) if args.batch >= 1 or args.batch == -1 else args.batch
    settings = dict(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=batch,
                    patience=args.patience, device=args.device, workers=args.workers,
                    fraction=args.fraction, seed=args.seed, deterministic=True,
                    project=str(RUNS / "train"), exist_ok=True, plots=True)

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "training_settings.json", "w", encoding="utf-8") as f:
        json.dump({"models": args.models, **settings}, f, indent=2)

    for weights in args.models:
        name = weights.replace(".pt", "")
        print(f"\n=== Training {name} ===")
        model = YOLO(weights)
        model.train(name=name, **settings)


if __name__ == "__main__":
    main()

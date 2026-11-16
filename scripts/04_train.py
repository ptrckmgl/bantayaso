"""Train the BantayAso detector, and the comparison models, with identical settings.

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
    # Fixed (not AutoBatch) so every model gets the same batch size. 16 is the Ultralytics
    # default; gradients are still accumulated to an effective batch of 64 (nbs=64).
    ap.add_argument("--batch", type=float, default=16, help="images per batch (-1 = AutoBatch)")
    # Written out explicitly instead of optimizer=auto, so the choice is recorded and identical
    # for every model. These are the values 'auto' picks for runs under 10,000 optimizer steps
    # (ours: ceil(4121 / 64) * 100 = 6,500): AdamW, lr0 = 0.002 * 5 / (4 + 2 classes) = 0.00167.
    ap.add_argument("--optimizer", default="AdamW")
    ap.add_argument("--lr0", type=float, default=0.00167, help="initial learning rate")
    ap.add_argument("--momentum", type=float, default=0.9, help="AdamW beta1")
    ap.add_argument("--patience", type=int, default=20, help="stop after N epochs without improvement")
    ap.add_argument("--device", default="0", help="0 = first GPU, 'cpu', or 'mps' on Apple Silicon")
    ap.add_argument("--workers", type=int, default=4, help="lower to 2 or 0 if Windows crashes loading data")
    ap.add_argument("--fraction", type=float, default=1.0, help="train on a fraction of the data (testing)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tag", default="", help="run name suffix, e.g. v2 -> runs/train/yolo26n_v2 (keeps older runs)")
    ap.add_argument("--cache", default="false", choices=["false", "ram", "disk"],
                    help="cache decoded images to speed up loading (ram needs lots of free memory)")
    args = ap.parse_args()

    batch = int(args.batch) if args.batch >= 1 or args.batch == -1 else args.batch
    settings = dict(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=batch,
                    optimizer=args.optimizer, lr0=args.lr0, momentum=args.momentum,
                    patience=args.patience, device=args.device, workers=args.workers,
                    fraction=args.fraction, seed=args.seed, deterministic=True,
                    cache=False if args.cache == "false" else args.cache,
                    project=str(RUNS / "train"), exist_ok=True, plots=True)

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / f"training_settings{'_' + args.tag if args.tag else ''}.json", "w", encoding="utf-8") as f:
        json.dump({"models": args.models, **settings}, f, indent=2)

    for weights in args.models:
        name = weights.replace(".pt", "") + (f"_{args.tag}" if args.tag else "")
        print(f"\n=== Training {name} ===")
        model = YOLO(weights)
        model.train(name=name, **settings)


if __name__ == "__main__":
    main()

"""Export the trained model for the edge device.

    python scripts/06_export.py                      # NCNN (Raspberry Pi 5) + ONNX (laptop)
    python scripts/06_export.py --formats tflite     # Android phone
    python scripts/06_export.py --formats coreml     # iPhone (run this on a Mac)

The exported files are written next to runs/train/<model>/weights/best.pt.
"""
import argparse

from ultralytics import YOLO

from common import MERGED, RUNS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(RUNS / "train" / "yolo26n" / "weights" / "best.pt"))
    ap.add_argument("--formats", nargs="+", default=["ncnn", "onnx"])
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--int8", action="store_true", help="8-bit quantisation (tflite); smaller and faster")
    args = ap.parse_args()

    model = YOLO(args.weights)
    for fmt in args.formats:
        print(f"\n=== Exporting to {fmt} ===")
        extra = {"int8": True, "data": str(MERGED / "data.yaml")} if args.int8 and fmt == "tflite" else {}
        path = model.export(format=fmt, imgsz=args.imgsz, **extra)
        print(f"    -> {path}")


if __name__ == "__main__":
    main()

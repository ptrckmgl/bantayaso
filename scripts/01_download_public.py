"""Download the dog (and person) subsets of Open Images V7 and COCO 2017 with FiftyOne,
and export each one in YOLO format to data/raw/<name>/.

Usage:
    python scripts/01_download_public.py              # all FiftyOne sources in configs/sources.yaml
    python scripts/01_download_public.py --only coco  # one source
    python scripts/01_download_public.py --max-samples 300   # quick test run

FiftyOne caches the original downloads in ~/fiftyone; the YOLO export is what the merge step reads.
"""
import argparse
import random

import fiftyone as fo
import fiftyone.zoo as foz
from fiftyone import ViewField as F

from common import CONFIGS, RAW, load_yaml


def export_source(src, max_samples=None, seed=42):
    name = src["name"]
    n = max_samples or src["max_samples"]
    print(f"\n=== {name}: downloading up to {n} samples of {src['classes']} from {src['zoo_name']}")

    ds = foz.load_zoo_dataset(
        src["zoo_name"],
        split=src.get("split", "train"),
        label_types=["detections"],
        classes=src["classes"],
        max_samples=n,
        shuffle=True,
        seed=seed,
        dataset_name=f"bantayaso-{name}-{n}",
    )

    # Normalise label names (Open Images uses "Dog"/"Person", COCO uses "dog"/"person")
    # and keep only dog and person boxes.
    view = ds.map_labels("ground_truth", {"Dog": "dog", "Person": "person"})
    view = view.filter_labels("ground_truth", F("label").is_in(["dog", "person"]), only_matches=False)

    # Keep every image with a dog, plus a capped share of images without one (negatives).
    has_dog = F("ground_truth.detections").filter(F("label") == "dog").length() > 0
    dog_ids = view.match(has_dog).values("id")
    other_ids = view.match(~has_dog).values("id")
    frac = src.get("max_non_dog_fraction", 0.0)
    keep_other = int(len(dog_ids) * frac / max(1e-9, 1 - frac)) if frac > 0 else 0
    random.Random(seed).shuffle(other_ids)
    keep_ids = dog_ids + other_ids[:keep_other]
    view = view.select(keep_ids)
    print(f"    {len(dog_ids)} images with dogs, {min(keep_other, len(other_ids))} without (negatives)")

    out = RAW / name
    view.export(
        export_dir=str(out),
        dataset_type=fo.types.YOLOv5Dataset,
        label_field="ground_truth",
        split="train",          # the merge step makes our own train/val/test split
        classes=["dog", "person"],
    )
    print(f"    exported to {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="name of a single source from sources.yaml")
    ap.add_argument("--max-samples", type=int, help="override max_samples (for a quick test)")
    args = ap.parse_args()

    sources = load_yaml(CONFIGS / "sources.yaml")["fiftyone"]
    for src in sources:
        if args.only and src["name"] != args.only:
            continue
        export_source(src, args.max_samples)


if __name__ == "__main__":
    main()

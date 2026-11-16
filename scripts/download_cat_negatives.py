"""Download cat images with no dog and no person in them (COCO 2017) as hard negatives.

Exported to data/raw/negatives_cat/ with EMPTY label files, so the model learns that a cat is
not a dog. Kept as a separate source folder so it can be left out of a merge (move it out of
data/raw). Only COCO is used: its labels are exhaustive, so "no dog / no person box" really
means none is in the picture (Open Images labels are not exhaustive).

    python scripts/download_cat_negatives.py              # ~1,500 images
    python scripts/download_cat_negatives.py --n 300      # quick test
"""
import argparse
import shutil

import fiftyone.zoo as foz
import yaml
from fiftyone import ViewField as F

from common import RAW


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500, help="number of cat images to keep")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # download extra so enough remain after dropping images that also contain a dog or a person
    ds = foz.load_zoo_dataset("coco-2017", split="train", label_types=["detections"], classes=["cat"],
                              max_samples=args.n * 2, shuffle=True, seed=args.seed,
                              dataset_name=f"bantayaso-cat-negatives-{args.n * 2}")
    clean = ds.match(F("ground_truth.detections").filter(F("label").is_in(["dog", "person"])).length() == 0)
    paths = clean.values("filepath")[:args.n]
    print(f"{len(ds)} cat images downloaded, {len(clean)} without dog/person, keeping {len(paths)}")

    out = RAW / "negatives_cat"
    if out.exists():
        shutil.rmtree(out)
    (out / "images" / "train").mkdir(parents=True)
    (out / "labels" / "train").mkdir(parents=True)
    for p in paths:
        src = __import__("pathlib").Path(p)
        shutil.copy2(src, out / "images" / "train" / src.name)
        (out / "labels" / "train" / f"{src.stem}.txt").write_text("", encoding="utf-8")
    with open(out / "data.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"path": ".", "train": "images/train", "nc": 1, "names": ["cat"],
                        "note": "hard negatives: cat images with no dog or person; label files are empty",
                        "source": "COCO 2017 train (annotations CC BY 4.0; Flickr images under own licenses)"},
                       f, sort_keys=False)
    print(f"exported {len(paths)} images with empty labels to {out}")


if __name__ == "__main__":
    main()

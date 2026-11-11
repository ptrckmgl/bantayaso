"""Clean, merge and split every dataset in data/raw/ into data/merged/.

What it does (each step is logged for the "Data preparation" section of the paper):
  1. Maps every source's class names to ours (dog, person) using configs/classes.yaml;
     other classes are dropped.
  2. Cleaning: drops unreadable images and exact duplicates (same file hash), flags blurry
     images (optionally drops them), converts polygon labels to boxes, clips boxes to the
     image, drops malformed or tiny boxes.
  3. Split:
       - public data -> train / val / test_public (75 / 15 / 10 by image)
       - our own footage (data/raw/own) -> grouped by clip so frames of one clip never
         land in two splits:
           --own-mode test  (default) all own clips are the real-world test set
           --own-mode split own clips are split 50 / 15 / 35 into train / val / test
  4. Writes data/merged/data.yaml (+ data_public_test.yaml), results/dataset_stats.csv
     and results/cleaning_log.csv.

    python scripts/03_merge_datasets.py
    python scripts/03_merge_datasets.py --own-mode split --drop-blurry 60
"""
import argparse
import csv
import hashlib
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import yaml

from common import IMAGE_EXTS, MERGED, RAW, RESULTS, class_mapper, class_names, load_yaml

OWN = "own"
MIN_BOX = 0.002  # boxes narrower/shorter than 0.2% of the image are treated as label noise


def source_names(src_dir):
    for name in ("data.yaml", "dataset.yaml"):
        for p in src_dir.rglob(name):
            names = load_yaml(p).get("names")
            if isinstance(names, dict):
                names = [names[k] for k in sorted(names)]
            return names
    raise FileNotFoundError(f"no data.yaml or dataset.yaml in {src_dir}")


def label_path_for(img):
    parts = list(img.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "images":
            parts[i] = "labels"
            return Path(*parts).with_suffix(".txt")
    return img.with_suffix(".txt")


def clean_labels(lbl_path, src_names, mapper, log):
    """Return cleaned YOLO lines with our class ids."""
    if not lbl_path.exists():
        log["no_label_file(empty_image)"] += 1
        return []
    out = []
    for line in lbl_path.read_text(encoding="utf-8").splitlines():
        vals = line.split()
        if not vals:
            continue
        try:
            cls = int(float(vals[0]))
            nums = [float(v) for v in vals[1:]]
        except ValueError:
            log["malformed_line"] += 1
            continue
        if cls < 0 or cls >= len(src_names):
            log["unknown_class_id"] += 1
            continue
        ours = mapper(src_names[cls])
        if ours is None:
            log[f"dropped_class:{src_names[cls]}"] += 1
            continue
        if len(nums) == 4:
            cx, cy, w, h = nums
            x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        elif len(nums) >= 6 and len(nums) % 2 == 0:  # polygon -> bounding box
            xs, ys = nums[0::2], nums[1::2]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            log["polygon_to_box"] += 1
        else:
            log["malformed_line"] += 1
            continue
        c = [min(1.0, max(0.0, v)) for v in (x1, y1, x2, y2)]
        if c != [x1, y1, x2, y2]:
            log["box_clipped_to_image"] += 1
        x1, y1, x2, y2 = c
        w, h = x2 - x1, y2 - y1
        if w < MIN_BOX or h < MIN_BOX:
            log["tiny_or_empty_box_dropped"] += 1
            continue
        out.append(f"{ours} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {w:.6f} {h:.6f}")
    return out


def collect(src_dir, mapper, log, seen_hashes, blur_thr):
    names = source_names(src_dir)
    items = []
    imgs = [p for p in src_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTS and "images" in p.parts]
    # labelled copies first, so when two files are identical the one with labels is kept
    imgs.sort(key=lambda p: (not label_path_for(p).exists(), str(p)))
    for img in imgs:
        data = img.read_bytes()
        digest = hashlib.md5(data).hexdigest()
        if digest in seen_hashes:
            log["duplicate_image_dropped"] += 1
            continue
        im = cv2.imread(str(img), cv2.IMREAD_GRAYSCALE)
        if im is None:
            log["unreadable_image_dropped"] += 1
            continue
        blur = cv2.Laplacian(im, cv2.CV_64F).var()
        if blur < (blur_thr or 0):
            log["blurry_image_dropped"] += 1
            continue
        if blur < 60:
            log["blurry_image_flagged(kept)"] += 1
        seen_hashes.add(digest)
        items.append((img, clean_labels(label_path_for(img), names, mapper, log)))
    return items


def write_item(split, source, img, lines):
    stem = f"{source}--{img.stem}"
    (MERGED / split / "images").mkdir(parents=True, exist_ok=True)
    (MERGED / split / "labels").mkdir(parents=True, exist_ok=True)
    shutil.copy2(img, MERGED / split / "images" / f"{stem}{img.suffix.lower()}")
    (MERGED / split / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""),
                                                           encoding="utf-8")


def split_list(items, fracs, rng):
    items = list(items)
    rng.shuffle(items)
    n = len(items)
    cuts, acc = [], 0.0
    for f in fracs[:-1]:
        acc += f
        cuts.append(round(n * acc))
    bounds = [0, *cuts, n]
    return [items[bounds[i]:bounds[i + 1]] for i in range(len(fracs))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--own-mode", choices=["test", "split"], default="test")
    ap.add_argument("--drop-blurry", type=float, default=0,
                    help="drop images whose Laplacian variance is below this (0 = only flag)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    mapper, names = class_mapper(), class_names()
    if MERGED.exists():
        shutil.rmtree(MERGED)
    RESULTS.mkdir(exist_ok=True)

    sources = sorted(p for p in RAW.iterdir() if p.is_dir()) if RAW.exists() else []
    if not sources:
        raise SystemExit("data/raw/ is empty: run the download scripts first.")

    seen = set()
    logs = {}
    stats = defaultdict(Counter)  # (split, source) -> counts

    def record(split, source, img, lines):
        write_item(split, source, img, lines)
        s = stats[(split, source)]
        s["images"] += 1
        if not lines:
            s["empty_images"] += 1
        for ln in lines:
            s[f"{names[int(ln.split()[0])]}_boxes"] += 1

    for src in sources:
        log = Counter()
        items = collect(src, mapper, log, seen, args.drop_blurry)
        logs[src.name] = log
        print(f"{src.name}: {len(items)} images kept")
        if src.name == OWN:
            clips = defaultdict(list)
            for img, lines in items:
                clips[img.stem.split("__")[0]].append((img, lines))
            if args.own_mode == "test":
                parts = {"test": list(clips)}
            else:
                tr, va, te = split_list(clips, [0.50, 0.15, 0.35], rng)
                parts = {"train": tr, "val": va, "test": te}
            for split, clip_ids in parts.items():
                for cid in clip_ids:
                    for img, lines in clips[cid]:
                        record(split, src.name, img, lines)
        else:
            tr, va, te = split_list(items, [0.75, 0.15, 0.10], rng)
            for split, chunk in (("train", tr), ("val", va), ("test_public", te)):
                for img, lines in chunk:
                    record(split, src.name, img, lines)

    has_own_test = (MERGED / "test" / "images").exists()
    base = {"path": str(MERGED.resolve()), "train": "train/images", "val": "val/images",
            "names": {i: n for i, n in enumerate(names)}}
    main_cfg = dict(base, test="test/images" if has_own_test else "test_public/images")
    with open(MERGED / "data.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(main_cfg, f, sort_keys=False)
    with open(MERGED / "data_public_test.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(dict(base, test="test_public/images"), f, sort_keys=False)

    cols = ["images", "empty_images", *[f"{n}_boxes" for n in names]]
    with open(RESULTS / "dataset_stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["split", "source", *cols])
        for (split, source), c in sorted(stats.items()):
            w.writerow([split, source, *[c[k] for k in cols]])
    with open(RESULTS / "cleaning_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "action", "count"])
        for source, log in logs.items():
            for action, n in sorted(log.items()):
                w.writerow([source, action, n])

    print("\nSplit summary:")
    totals = defaultdict(Counter)
    for (split, _), c in stats.items():
        totals[split].update(c)
    for split, c in sorted(totals.items()):
        print(f"  {split:12s} " + "  ".join(f"{k}={c[k]}" for k in cols))
    print(f"\nTest set in data.yaml: {'own footage' if has_own_test else 'public test split'}")
    print(f"Wrote {MERGED / 'data.yaml'}, results/dataset_stats.csv, results/cleaning_log.csv")


if __name__ == "__main__":
    main()

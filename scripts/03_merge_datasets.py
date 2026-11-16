"""Clean, merge and split every dataset in data/raw/ into data/merged/.

What it does (each step is logged for the "Data preparation" section of the paper):
  1. Maps every source's class names to ours (dog, person) using configs/classes.yaml;
     other classes are dropped.
  2. Cleaning: drops unreadable images and exact duplicates (same file hash), drops
     near-duplicates of an image already kept from another source (64-bit dHash, Hamming
     distance <= 6), flags blurry images (kept by default; optionally dropped), converts
     polygon labels to boxes, clips boxes to the image, drops malformed or tiny boxes.
  3. Split:
       - public data -> train / val / test_public (75 / 15 / 10 of the images). Images are
         split in groups: Roboflow copies of one original and near-duplicate images
         (e.g. consecutive video frames, dHash distance <= 6) share a group, and a group
         never straddles two splits
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
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

from common import IMAGE_EXTS, MERGED, RAW, RESULTS, class_mapper, class_names, load_yaml

OWN = "own"
MIN_BOX = 0.002  # boxes narrower/shorter than 0.2% of the image are treated as label noise
NEAR_DUP = 6     # max Hamming distance (of 64 bits) between dHashes to call two images near-duplicates
BLUR_FLAG = 60   # Laplacian variance below this is logged as blurry


def dhash(gray):
    """64-bit difference hash: is each pixel brighter than its right neighbour on a 9x8 thumbnail."""
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int(np.packbits(bits).view(">u8")[0])


def near_matches(a, b, block=512):
    """For every hash in a, the indices of hashes in b within NEAR_DUP bits (numpy XOR + popcount)."""
    a, b = np.asarray(a, np.uint64), np.asarray(b, np.uint64)
    out = []
    for s in range(0, len(a), block):
        d = np.bitwise_count(a[s:s + block, None] ^ b[None, :])
        out.extend(np.flatnonzero(row <= NEAR_DUP) for row in d)
    return out


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


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


def collect(src_dir, mapper, log, seen_hashes, blur_thr, other_dhashes):
    """Return [(img, lines, dhash)]. other_dhashes: dHashes kept from earlier sources."""
    names = source_names(src_dir)
    items = []
    other = np.asarray(other_dhashes, np.uint64)
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
        dh = dhash(im)
        if len(other) and np.bitwise_count(other ^ np.uint64(dh)).min() <= NEAR_DUP:
            log["near_duplicate_cross_source_dropped"] += 1
            continue
        blur = cv2.Laplacian(im, cv2.CV_64F).var()
        if blur < (blur_thr or 0):
            log[f"blurry_image_dropped(laplacian_var<{blur_thr:g})"] += 1
            continue
        if blur < BLUR_FLAG:
            log[f"blurry_image_flagged_kept(laplacian_var<{BLUR_FLAG})"] += 1
        seen_hashes.add(digest)
        items.append((img, clean_labels(label_path_for(img), names, mapper, log), dh))
    return items


SCENE_PATTERNS = [
    # CCTV exports name frames after the camera or video they came from, e.g.
    #   0bb4d2ed-2e0a-4056-9b93-7eca41100ec8 1670000624 _jpeg  (video UUID + timestamp)
    #   200769_1683016759_1_0_jpeg                            (camera id + timestamp)
    #   1135_2023-03-24-11_47_18_jpeg                         (camera id + date)
    #   08-02-2023_10-15-00_jpg                               (recording day)
    re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\d{6,}"),
    re.compile(r"^(\d+)_1\d{9}_"),
    re.compile(r"^(\d+)_\d{4}-\d\d-\d\d"),
    re.compile(r"^(\d\d-\d\d-\d{4})_"),
]


def scene_key(stem):
    """Camera / video id from a frame's file name, or None if the name has none."""
    base = stem.split(".rf.")[0]
    for pat in SCENE_PATTERNS:
        m = pat.match(base)
        if m:
            return m.group(1)
    return None


def cap_group(group, n):
    """Keep at most n images of a group, evenly spaced in file-name (= time) order."""
    if not n or len(group) <= n:
        return group
    group = sorted(group, key=lambda it: it[0].name)
    step = len(group) / n
    return [group[int(i * step)] for i in range(n)]


def box_counts(lines):
    """(dog boxes, person boxes) of one image's cleaned label lines."""
    c = Counter(ln.split()[0] for ln in lines)
    return c["0"], c["1"]


def thin_repeated_frames(items, max_bits, log):
    """Within each camera / video (see scene_key), walk the frames in time (file-name) order and drop
    a frame only if an already-kept frame of the same camera looks nearly the same (dHash distance
    <= max_bits) AND has the same number of dog and person boxes. A frame showing anything new
    (different scene, lighting, or dog / person count) is kept."""
    by_scene = defaultdict(list)
    out = []
    for it in items:
        s = scene_key(it[0].stem)
        (by_scene[s] if s is not None else out).append(it)
    for s, frames in by_scene.items():
        frames.sort(key=lambda it: it[0].name)
        kept = []  # (dhash, counts)
        for it in frames:
            dh, cnt = np.uint64(it[2]), box_counts(it[1])
            if any(c == cnt and int(np.bitwise_count(dh ^ k)) <= max_bits for k, c in kept):
                log[f"repeated_frame_dropped(same_camera,dhash<={max_bits},same_box_counts)"] += 1
                continue
            kept.append((dh, cnt))
            out.append(it)
    return out


def group_items(items, log, by_scene=False):
    """Group Roboflow copies of one original ('<original>.rf.<hash>') and near-duplicate images.
    by_scene: also put all frames of one camera / video (see scene_key) in the same group."""
    uf = UnionFind(len(items))
    first = {}
    for i, (img, _, _) in enumerate(items):
        key = img.stem.split(".rf.")[0]
        if key in first:
            uf.union(i, first[key])
        else:
            first[key] = i
    if by_scene:
        first_scene = {}
        for i, (img, _, _) in enumerate(items):
            s = scene_key(img.stem)
            if s is None:
                continue
            log["images_with_camera_or_video_id"] += 1
            if s in first_scene:
                uf.union(i, first_scene[s])
            else:
                first_scene[s] = i
        log["camera_or_video_ids"] = len(first_scene)
    rf_groups = len({uf.find(i) for i in range(len(items))})
    pairs = 0
    for i, js in enumerate(near_matches([d for *_, d in items], [d for *_, d in items])):
        for j in js:
            if j > i:
                pairs += 1
                uf.union(i, int(j))
    groups = defaultdict(list)
    for i, it in enumerate(items):
        groups[uf.find(i)].append(it)
    groups = list(groups.values())
    log["split_groups_roboflow_copies_only"] = rf_groups
    log["near_duplicate_pairs_within_source"] = pairs
    log["split_groups"] = len(groups)
    log["images_sharing_a_group"] = sum(len(g) for g in groups if len(g) > 1)
    log["largest_group_images"] = max((len(g) for g in groups), default=0)
    return groups


def split_groups_by_images(groups, fracs, rng):
    """Shuffle whole groups, then cut where the running image count reaches each fraction."""
    groups = list(groups)
    rng.shuffle(groups)
    total = sum(len(g) for g in groups)
    targets = np.cumsum(fracs)[:-1] * total
    parts = [[] for _ in fracs]
    k, acc = 0, 0
    for g in groups:
        while k < len(targets) and acc >= targets[k]:
            k += 1
        parts[k].append(g)
        acc += len(g)
    return parts


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
    ap.add_argument("--split-by-scene", action="store_true",
                    help="keep all frames of one camera / video in the same split (no scene leakage)")
    ap.add_argument("--thin-repeats", type=int, default=0,
                    help="drop a frame if a kept frame of the same camera/video is within this many dHash "
                         "bits AND has the same dog/person box counts (e.g. 10); 0 = off")
    ap.add_argument("--max-per-group", type=int, default=0,
                    help="keep at most N images per group (camera, video or near-duplicate set); 0 = all")
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
    kept_dhashes = []  # from sources already processed, for the cross-source near-duplicate check
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
        items = collect(src, mapper, log, seen, args.drop_blurry, kept_dhashes)
        kept_dhashes.extend(d for *_, d in items)
        logs[src.name] = log
        print(f"{src.name}: {len(items)} images kept")
        if src.name == OWN:
            clips = defaultdict(list)
            for img, lines, _ in items:
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
            # Roboflow exports name files '<original>_jpg.rf.<hash>.jpg'. Copies of one original
            # (augmentations or re-exports) share the part before '.rf.'; near-duplicate images
            # (e.g. neighbouring frames of one video) are joined to the same group. Each group is
            # split as a unit, so near-identical images can never leak between train / val / test.
            if args.thin_repeats:
                items = thin_repeated_frames(items, args.thin_repeats, log)
            groups = group_items(items, log, by_scene=args.split_by_scene)
            if args.max_per_group:
                before = sum(len(g) for g in groups)
                groups = [cap_group(g, args.max_per_group) for g in groups]
                log[f"repeated_frames_dropped(max_{args.max_per_group}_per_group)"] = \
                    before - sum(len(g) for g in groups)
            groups.sort(key=lambda g: min(str(it[0]) for it in g))  # deterministic order before shuffling
            tr, va, te = split_groups_by_images(groups, [0.75, 0.15, 0.10], rng)
            for split, gs in (("train", tr), ("val", va), ("test_public", te)):
                for g in gs:
                    for img, lines, _ in g:
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

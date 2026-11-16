"""Audit a Roboflow YOLO export: classes, boxes, sizes, exact + near-duplicate images,
and overlap with other raw sets (coco, openimages). Writes JSON + text report."""
import sys, os, json, hashlib, collections
import numpy as np
from PIL import Image

root = sys.argv[1]           # data/raw
target = sys.argv[2]         # folder name of the set to audit
out = sys.argv[3]

def yaml_names(p):
    for line in open(p, encoding="utf-8"):
        if line.strip().startswith("names:"):
            return [s.strip().strip("'\"") for s in line.split("[",1)[1].rsplit("]",1)[0].split(",")]

def dhash(path, size=8):
    im = Image.open(path).convert("L").resize((size+1, size), Image.BILINEAR)
    a = np.asarray(im, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return np.packbits(bits)

records = []   # (set, split, relpath, md5, dhash, w, h)
def scan(setname, splits):
    for split, imgdir in splits:
        if not os.path.isdir(imgdir): continue
        for f in sorted(os.listdir(imgdir)):
            p = os.path.join(imgdir, f)
            try:
                with Image.open(p) as im: w, h = im.size
                md5 = hashlib.md5(open(p, "rb").read()).hexdigest()
                records.append((setname, split, f, md5, dhash(p), w, h))
            except Exception as e:
                print("bad image", p, e)

T = os.path.join(root, target)
scan(target, [(s, os.path.join(T, s, "images")) for s in ("train", "valid", "test")])
for other in ("coco", "openimages"):
    d = os.path.join(root, other, "images")
    if os.path.isdir(d):
        subs = [x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))]
        scan(other, [(s, os.path.join(d, s)) for s in subs] or [("all", d)])

rep = {}
names = yaml_names(os.path.join(T, "data.yaml"))
rep["names"] = names
boxes = collections.Counter(); imgs_with = collections.Counter(); empty = 0; small = collections.Counter()
per_split = collections.Counter()
for s in ("train", "valid", "test"):
    ld = os.path.join(T, s, "labels")
    if not os.path.isdir(ld): continue
    for f in os.listdir(ld):
        per_split[s] += 1
        seen = set(); n = 0
        for line in open(os.path.join(ld, f)):
            parts = line.split()
            if len(parts) < 5: continue
            c = names[int(parts[0])]; n += 1
            boxes[c] += 1; seen.add(c)
            if float(parts[3]) * float(parts[4]) < 0.0025: small[c] += 1   # <~5% side
            if len(parts) > 5: boxes["_polygon_rows"] += 1
        if n == 0: empty += 1
        for c in seen: imgs_with[c] += 1
combo = collections.Counter()
rep.update(boxes=boxes, images_with_class=imgs_with, empty_label_files=empty,
           tiny_boxes=small, label_files_per_split=per_split)

tr = [r for r in records if r[0] == target]
sizes = collections.Counter(f"{r[5]}x{r[6]}" for r in tr)
rep["image_sizes_top"] = sizes.most_common(8)

# exact duplicates
by_md5 = collections.defaultdict(list)
for r in records: by_md5[r[3]].append((r[0], r[1], r[2]))
exact = [v for v in by_md5.values() if len(v) > 1]
rep["exact_dup_groups"] = len(exact)
rep["exact_dup_cross_split_in_target"] = sum(1 for v in exact if len({x[1] for x in v if x[0]==target}) > 1)
rep["exact_dup_with_other_sets"] = sum(1 for v in exact if any(x[0]==target for x in v) and any(x[0]!=target for x in v))

# near duplicates (dHash hamming <= thr) via union-find
H = np.stack([r[4] for r in records])  # N x 8 uint8
pop = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
N = len(records); parent = list(range(N))
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
THR = int(os.environ.get("THR", 6))
pairs_cross_split = 0; pairs_other = 0; pairs = 0
for i in range(0, N, 512):
    blk = H[i:i+512]
    d = pop[np.bitwise_xor(blk[:, None, :], H[None, :, :])].sum(-1)
    ii, jj = np.nonzero(d <= THR)
    for a, b in zip(ii + i, jj):
        if b <= a: continue
        pairs += 1
        ra, rb = records[a], records[b]
        if ra[0] == target and rb[0] == target and ra[1] != rb[1]: pairs_cross_split += 1
        if (ra[0] == target) != (rb[0] == target): pairs_other += 1
        pa, pb = find(a), find(b)
        if pa != pb: parent[pa] = pb
groups = collections.defaultdict(list)
for k in range(N): groups[find(k)].append(k)
tgt_idx = [k for k in range(N) if records[k][0] == target]
tgt_groups = {find(k) for k in tgt_idx}
rep["near_dup_threshold"] = THR
rep["target_images"] = len(tgt_idx)
rep["target_unique_groups"] = len(tgt_groups)
rep["near_dup_pairs"] = pairs
rep["near_dup_pairs_cross_split_in_target"] = pairs_cross_split
rep["near_dup_pairs_with_coco_or_oi"] = pairs_other
big = sorted((g for g in groups.values() if len(g) > 1 and any(records[k][0]==target for k in g)), key=len, reverse=True)
rep["largest_groups"] = [[f"{records[k][0]}/{records[k][1]}/{records[k][2]}" for k in g[:6]] + [f"(size {len(g)})"] for g in big[:8]]
rep["group_size_hist"] = collections.Counter(min(len(g), 10) for g in groups.values() if any(records[k][0]==target for k in g))
json.dump(rep, open(out, "w"), indent=1, default=lambda o: dict(o) if isinstance(o, collections.Counter) else str(o))
print(json.dumps(rep, indent=1, default=lambda o: dict(o) if isinstance(o, collections.Counter) else str(o)))

"""Evaluate weights on test_public subsets by source (CCTV/Roboflow, COCO+OpenImages, cat negatives)."""
import argparse, json
from pathlib import Path
import yaml
from ultralytics import YOLO
from common import MERGED, RESULTS

GROUPS = {"cctv_roboflow": ("stray dogs.v3i", "Stray Dog Dete"), "coco_oi": ("coco--", "openimages"), "cat_negatives": ("negatives",)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", nargs="+", required=True)
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--out", default=str(RESULTS / "v3" / "subset_eval.json"))
    a = ap.parse_args()
    imgs = sorted((MERGED / "test_public" / "images").iterdir())
    work = RESULTS / "v3" / "subsets"; work.mkdir(parents=True, exist_ok=True)
    res = {}
    for g, prefixes in GROUPS.items():
        sel = [p for p in imgs if p.name.startswith(prefixes)]
        lst = work / f"{g}.txt"; lst.write_text("\n".join(str(p.resolve()) for p in sel))
        y = work / f"{g}.yaml"; y.write_text(yaml.safe_dump({"path": str(MERGED.resolve()), "train": str(lst), "val": str(lst), "names": {0: "dog", 1: "person"}}))
        for w, n in zip(a.weights, a.names):
            m = YOLO(w).val(data=str(y), imgsz=640, batch=8, workers=2, device="0", verbose=False, plots=False)
            b = m.box
            res[f"{g}|{n}"] = {"images": len(sel), "P": float(b.mp), "R": float(b.mr), "mAP50": float(b.map50), "mAP50-95": float(b.map),
                               "dog_AP50": float(b.ap50[0]) if len(b.ap50) > 0 else None}
            print(g, n, res[f"{g}|{n}"], flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1))

if __name__ == "__main__":
    main()

"""Turn our own videos (phone clips of street / campus dogs) into frames for labeling.

Name each video after where and when it was filmed, e.g. campus-gate_2026-11-18_am.mp4.
Frames are saved as <clip>__f00012.jpg; the part before "__" is the clip id, which the
merge step uses to keep every frame of a clip in the same split.

    python scripts/extract_frames.py data/videos --fps 1
    -> data/frames/<clip>__fNNNNN.jpg   (upload this folder to Roboflow and label it)
"""
import argparse
from pathlib import Path

import cv2

from common import DATA

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp"}


def extract(video, out_dir, fps):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"  ! could not open {video}")
        return 0
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))
    clip = video.stem.replace("__", "_")
    saved = idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            cv2.imwrite(str(out_dir / f"{clip}__f{idx:05d}.jpg"), frame)
            saved += 1
        idx += 1
    cap.release()
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", type=Path, help="folder of videos (or a single video)")
    ap.add_argument("--out", type=Path, default=DATA / "frames")
    ap.add_argument("--fps", type=float, default=1.0, help="frames saved per second of video")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    videos = [args.videos] if args.videos.is_file() else sorted(
        p for p in args.videos.rglob("*") if p.suffix.lower() in VIDEO_EXTS)
    total = 0
    for v in videos:
        n = extract(v, args.out, args.fps)
        print(f"{v.name}: {n} frames")
        total += n
    print(f"\n{total} frames from {len(videos)} videos saved to {args.out}")


if __name__ == "__main__":
    main()

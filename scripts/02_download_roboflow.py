"""Download the Roboflow Universe datasets listed in configs/sources.yaml to data/raw/<name>/.

Needs a free Roboflow API key (roboflow.com -> Settings -> API Keys), passed as an
environment variable so it never ends up in git:

    Windows PowerShell:  $env:ROBOFLOW_API_KEY="your_key"
    macOS / Linux:       export ROBOFLOW_API_KEY=your_key

    python scripts/02_download_roboflow.py
"""
import argparse
import os
import sys

from roboflow import Roboflow

from common import CONFIGS, RAW, load_yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="name of a single source from sources.yaml")
    args = ap.parse_args()

    key = os.environ.get("ROBOFLOW_API_KEY")
    if not key:
        sys.exit("Set the ROBOFLOW_API_KEY environment variable first (see the top of this file).")

    rf = Roboflow(api_key=key)
    for src in load_yaml(CONFIGS / "sources.yaml").get("roboflow", []):
        if args.only and src["name"] != args.only:
            continue
        out = RAW / src["name"]
        print(f"\n=== {src['name']}: {src['workspace']}/{src['project']} v{src['version']} ({src['license']})")
        project = rf.workspace(src["workspace"]).project(src["project"])
        project.version(src["version"]).download("yolov8", location=str(out), overwrite=True)
        print(f"    downloaded to {out}")


if __name__ == "__main__":
    main()

"""Shared paths and helpers for the StrayWatch ML scripts."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
DATA = ROOT / "data"
RAW = DATA / "raw"
MERGED = DATA / "merged"
RUNS = ROOT / "runs"
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def class_names():
    return load_yaml(CONFIGS / "classes.yaml")["names"]


def class_mapper():
    """Return a function mapping a source class name to our class id (or None to drop it)."""
    cfg = load_yaml(CONFIGS / "classes.yaml")
    names = cfg["names"]
    lookup = {}
    for target, aliases in cfg["map"].items():
        for alias in [target, *aliases]:
            lookup[str(alias).strip().lower()] = names.index(target)

    def mapper(source_name):
        return lookup.get(str(source_name).strip().lower())

    return mapper

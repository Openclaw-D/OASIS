"""Resolve this project's own same-Mac clean build copy, when prepared."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
BUILD_BASE = Path.home() / "Library/Application Support/01-WORLD/native-build-v1"
LOCATION_RECEIPT = ROOT / "logs/native-build-location.json"


def build_locations():
    if not LOCATION_RECEIPT.is_file():
        return ROOT / "project/OasisNative.uproject", ROOT / "delivery"
    receipt = json.loads(LOCATION_RECEIPT.read_text())
    project = Path(receipt["build_project"]).resolve()
    archive = Path(receipt["archive_directory"]).resolve()
    if receipt["canonical_project"] != str(ROOT / "project/OasisNative.uproject"):
        raise RuntimeError("Build receipt belongs to another source project")
    if not project.is_relative_to(BUILD_BASE) or not archive.is_relative_to(BUILD_BASE):
        raise RuntimeError("Clean build paths are outside the authorized same-Mac build root")
    if not project.is_file():
        raise RuntimeError("Prepared build project is missing")
    return project, archive

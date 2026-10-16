"""Stage the existing public map sources and a bounded Shanghai arterial overview."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
data = ROOT / "project/Content/NativeData"
data.mkdir(parents=True, exist_ok=True)
earth = ROOT.parent / "data/earth-overview.geojson"
city = ROOT.parent / "data/shanghai-roads-source.json"
shutil.copyfile(earth, data / earth.name)
source = json.loads(city.read_text())
types = {"motorway", "trunk", "primary", "secondary", "tertiary",
         "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
paths = []
for element in source["elements"]:
    if element.get("tags", {}).get("highway") not in types:
        continue
    coordinates = [[point["lon"], point["lat"]] for point in element.get("geometry", [])]
    if len(coordinates) > 1:
        paths.append(coordinates)
overview = {"source": "OpenStreetMap contributors", "scope": "Public community-mapped arterial road overview, not a survey",
            "paths": paths}
(data / "shanghai-overview.json").write_text(json.dumps(overview, separators=(",", ":")) + "\n")
receipt = {"earth_source_sha256": hashlib.sha256(earth.read_bytes()).hexdigest(),
           "city_source_sha256": hashlib.sha256(city.read_bytes()).hexdigest(),
           "arterial_paths": len(paths), "arterial_points": sum(map(len, paths)),
           "sources": ["Natural Earth generalized country boundaries", "OpenStreetMap contributors"],
           "runtime_picking_and_rendering_verified": False}
(ROOT / "logs/native-map-payload.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))

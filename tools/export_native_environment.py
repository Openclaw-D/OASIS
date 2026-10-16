"""Export the authored ground, river, roads and synthetic planting without changing the master."""
from pathlib import Path
import hashlib
import json
import bpy

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(json.loads((ROOT / "production-paths.json").read_text())["asset_root"])
source = OUT / "source/lujiazui-hero-v1.blend"
before = hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(source))
objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"
           and any(col.name in {"Ground", "Roads", "Nature"} for col in obj.users_collection)]
if not objects:
    raise RuntimeError("Authored environment objects are missing")
members = [{"name": obj.name, "entity_id": obj.get("entity_id"),
            "provenance": obj.get("provenance")} for obj in objects]
bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects["WhiteGround"]
bpy.ops.object.join()
joined = bpy.context.view_layer.objects.active
joined.name = "Lujiazui_Environment"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
output = OUT / "exports/native-import/lujiazui-environment.fbx"
bpy.ops.export_scene.fbx(filepath=str(output), use_selection=True, object_types={"MESH"},
                         axis_forward="-Y", axis_up="Z", global_scale=1,
                         apply_unit_scale=True, use_custom_props=False, bake_anim=False)
if hashlib.sha256(source.read_bytes()).hexdigest() != before:
    raise RuntimeError("Master source changed")
receipt = {"file": str(output), "bytes": output.stat().st_size,
           "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
           "master_sha256": before, "master_preserved": True,
           "member_count": len(members), "members": members,
           "pivot_enu_m": [0, 0, 0], "planned_cesium_esu_cm": [0, 0, 0],
           "ground_elevation": "Flat authored reference at zero; surveyed elevation unknown",
           "trees": "Synthetic park planting estimate, not individually mapped trees",
           "source_units": "meters", "native_import_verified": False}
(OUT / "exports/native-import/environment-manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({key: value for key, value in receipt.items() if key != "members"}, indent=2))

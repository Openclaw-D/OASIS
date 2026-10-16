"""Run inside the real Unreal Editor after the native target has built."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import traceback
import unreal

ROOT = Path(__file__).resolve().parents[1]
receipt = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "passed": False}


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def length(vector):
    return math.sqrt(sum(value * value for value in vector))


try:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not levels.new_level("/Game/Calibration/AxisProbe"):
        raise RuntimeError("Could not create the owned axis calibration map")
    geo = actors.spawn_actor_from_class(unreal.CesiumGeoreference, unreal.Vector())
    geo.set_origin_longitude_latitude_height(unreal.Vector(121.501909, 31.2364814, 0))
    origin = geo.transform_longitude_latitude_height_position_to_unreal(
        unreal.Vector(121.501909, 31.2364814, 0))
    raised = geo.transform_longitude_latitude_height_position_to_unreal(
        unreal.Vector(121.501909, 31.2364814, 1))
    llh = geo.transform_unreal_position_to_longitude_latitude_height(raised)
    receipt["cesium_runtime_loaded"] = True
    receipt["georeference"] = {
        "origin_unreal_cm": xyz(origin), "raised_one_meter_unreal_cm": xyz(raised),
        "raised_roundtrip_llh": xyz(llh),
    }
    if length(xyz(origin)) > 0.01 or length([raised.x, raised.y, raised.z - 100]) > 0.01:
        raise RuntimeError("Cesium one-meter georeference check failed")
    if abs(llh.x - 121.501909) > 1e-7 or abs(llh.y - 31.2364814) > 1e-7 or abs(llh.z - 1) > 0.001:
        raise RuntimeError("Cesium LLH roundtrip failed")

    options = unreal.FbxImportUI()
    options.set_editor_property("automated_import_should_detect_type", False)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_as_skeletal", False)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    data = options.get_editor_property("static_mesh_import_data")
    for name, value in {
        "combine_meshes": False, "auto_generate_collision": False,
        "generate_lightmap_u_vs": False, "convert_scene": True,
        "convert_scene_unit": True, "force_front_x_axis": False,
        "transform_vertex_to_absolute": True, "bake_pivot_in_vertex": False,
    }.items():
        data.set_editor_property(name, value)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(ROOT / "dependencies/native-axis-probe/axis_probe.fbx"))
    task.set_editor_property("destination_path", "/Game/Calibration/Axes")
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("factory", unreal.FbxFactory())
    task.set_editor_property("options", options)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    meshes = {}
    for path in task.get_editor_property("imported_object_paths"):
        mesh = unreal.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            continue
        bounds = mesh.get_bounding_box()
        center = [(a + b) / 2 for a, b in zip(xyz(bounds.min), xyz(bounds.max))]
        dimensions = [b - a for a, b in zip(xyz(bounds.min), xyz(bounds.max))]
        meshes[mesh.get_name()] = {"path": path, "center_cm": center, "dimensions_cm": dimensions}
    receipt["imported_meshes"] = meshes
    marker_data = {}
    for marker in ["UnitCube", "AxisE", "AxisN", "AxisU"]:
        matches = [value for name, value in meshes.items() if name.endswith(marker)]
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one imported mesh for " + marker)
        marker_data[marker] = matches[0]
    if any(abs(side - 100) > 0.01 for side in marker_data["UnitCube"]["dimensions_cm"]):
        raise RuntimeError("Imported unit cube is not 100 centimeters")
    base = marker_data["UnitCube"]["center_cm"]
    columns = [[(v - b) / scale for v, b in zip(marker_data[name]["center_cm"], base)]
               for name, scale in [("AxisE", 2), ("AxisN", 3), ("AxisU", 4)]]
    if any(abs(length(column) - 100) > 0.01 for column in columns):
        raise RuntimeError("Axis marker scale differs from one meter")
    for i in range(3):
        for j in range(i + 1, 3):
            if abs(sum(a * b for a, b in zip(columns[i], columns[j]))) > 0.1:
                raise RuntimeError("Imported basis is not orthogonal")
    expected = [[100, 0, 0], [0, -100, 0], [0, 0, 100]]
    yaw = -math.degrees(math.atan2(columns[0][1], columns[0][0]))
    cosine, sine = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    corrected = [[cosine * x - sine * y, sine * x + cosine * y, z] for x, y, z in columns]
    if any(abs(a - b) > 0.01 for column, target in zip(corrected, expected) for a, b in zip(column, target)):
        raise RuntimeError("Imported basis needs more than the supported root yaw correction")
    receipt["axis_import"] = {
        "basis_cm_per_enu_meter_columns": columns,
        "root_yaw_correction_degrees": yaw,
        "corrected_basis_columns": corrected,
        "unit_cube_dimensions_cm": marker_data["UnitCube"]["dimensions_cm"],
    }
    levels.save_current_level()
    receipt["passed"] = True
except Exception:
    receipt["error"] = traceback.format_exc()
    unreal.log_error(receipt["error"])
finally:
    (ROOT / "logs/native-axis-gate.json").write_text(json.dumps(receipt, indent=2) + "\n")
    unreal.log("OASIS_AXIS_GATE=" + json.dumps(receipt))
    unreal.SystemLibrary.quit_editor()

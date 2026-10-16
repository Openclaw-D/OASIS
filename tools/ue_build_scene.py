"""Create the actual Native scene from audited FBX files, using the measured import basis."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import traceback
import unreal

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(json.loads((ROOT / "production-paths.json").read_text())["asset_root"])
receipt = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
           "scope": "Real Unreal imports and authored scene; visual/runtime acceptance remains separate"}
tools = unreal.AssetToolsHelpers.get_asset_tools()
materials = unreal.MaterialEditingLibrary
assets = unreal.EditorAssetLibrary


def save(asset):
    assets.save_loaded_asset(asset, only_if_is_dirty=False)


def material(name, value, unlit=False):
    path = "/Game/Oasis/Materials/" + name
    result = unreal.load_asset(path)
    if result is None:
        result = tools.create_asset(name, "/Game/Oasis/Materials", unreal.Material, unreal.MaterialFactoryNew())
    materials.delete_all_material_expressions(result)
    if unlit:
        result.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    vector = materials.create_material_expression(result, unreal.MaterialExpressionConstant3Vector)
    vector.set_editor_property("constant", unreal.LinearColor(value, value, value, 1))
    materials.connect_material_property(vector, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR if unlit else unreal.MaterialProperty.MP_BASE_COLOR)
    if not unlit:
        rough = materials.create_material_expression(result, unreal.MaterialExpressionConstant)
        rough.set_editor_property("r", .8)
        materials.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        spec = materials.create_material_expression(result, unreal.MaterialExpressionConstant)
        spec.set_editor_property("r", .15)
        materials.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
        fill = materials.create_material_expression(result, unreal.MaterialExpressionConstant3Vector)
        fill.set_editor_property("constant", unreal.LinearColor(value * .12, value * .12, value * .12, 1))
        materials.connect_material_property(fill, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    materials.recompile_material(result)
    save(result)
    return result


def outline():
    name = "PP_OasisInk"
    result = unreal.load_asset("/Game/Oasis/Materials/" + name)
    if result is None:
        result = tools.create_asset(name, "/Game/Oasis/Materials", unreal.Material, unreal.MaterialFactoryNew())
    materials.delete_all_material_expressions(result)
    result.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    result.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_BEFORE_DOF)
    node = materials.create_material_expression(result, unreal.MaterialExpressionCustom)
    node.set_editor_property("code", (ROOT / "tools/oasis_outline.hlsl").read_text())
    node.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs = []
    for name in ["SourceColor", "Depth", "Normals", "Stencil", "CustomDepth", "LineWidth"]:
        item = unreal.CustomInput()
        item.set_editor_property("input_name", name)
        inputs.append(item)
    node.set_editor_property("inputs", inputs)
    for name, texture in [
        ("SourceColor", unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0),
        ("Depth", unreal.SceneTextureId.PPI_SCENE_DEPTH),
        ("Normals", unreal.SceneTextureId.PPI_WORLD_NORMAL),
        ("Stencil", unreal.SceneTextureId.PPI_CUSTOM_STENCIL),
        ("CustomDepth", unreal.SceneTextureId.PPI_CUSTOM_DEPTH),
    ]:
        expression = materials.create_material_expression(result, unreal.MaterialExpressionSceneTexture)
        expression.set_editor_property("scene_texture_id", texture)
        materials.connect_material_expressions(expression, "Color", node, name)
    width = materials.create_material_expression(result, unreal.MaterialExpressionScalarParameter)
    width.set_editor_property("parameter_name", "LineWidth")
    width.set_editor_property("default_value", 1.1)
    materials.connect_material_expressions(width, "", node, "LineWidth")
    materials.connect_material_property(node, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    materials.recompile_material(result)
    save(result)
    return result


def import_mesh(path, label):
    options = unreal.FbxImportUI()
    options.set_editor_property("automated_import_should_detect_type", False)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_as_skeletal", False)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    data = options.get_editor_property("static_mesh_import_data")
    for name, value in {"combine_meshes": True, "auto_generate_collision": False,
                        "generate_lightmap_u_vs": False, "convert_scene": True,
                        "convert_scene_unit": True, "force_front_x_axis": False,
                        "transform_vertex_to_absolute": True, "bake_pivot_in_vertex": False}.items():
        data.set_editor_property(name, value)
    task = unreal.AssetImportTask()
    for name, value in {"filename": str(path), "destination_path": "/Game/Oasis/Geometry",
                        "destination_name": label.replace("-", "_"), "automated": True,
                        "save": True, "replace_existing": True, "factory": unreal.FbxFactory(),
                        "options": options}.items():
        task.set_editor_property(name, value)
    tools.import_asset_tasks([task])
    meshes = [unreal.load_asset(p) for p in task.get_editor_property("imported_object_paths")]
    meshes = [mesh for mesh in meshes if isinstance(mesh, unreal.StaticMesh)]
    if len(meshes) != 1:
        raise RuntimeError("Expected one combined native mesh: " + label)
    return meshes[0]


try:
    basis = json.loads((ROOT / "logs/native-axis-gate.json").read_text())
    if not basis["passed"]:
        raise RuntimeError("Native units/basis gate has not passed")
    materials_by_name = {name: material(name, value, unlit) for name, value, unlit in [
        ("M_Mono_Hero", .90, False), ("M_Mono_Building", .91, False),
        ("M_Mono_Ground", .96, False), ("M_Mono_Water", .85, False),
        ("M_Mono_Detail", .16, False), ("M_Mono_Ink", .003, True),
        ("M_Mono_Road", .86, False), ("M_Mono_Nature", .85, False),
        ("M_Mono_Globe", .95, False),
    ]}
    pp_material = outline()
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if assets.does_asset_exist("/Game/Oasis/Maps/Oasis"):
        if not levels.load_level("/Game/Oasis/Maps/Oasis"):
            raise RuntimeError("Could not load the owned generated map")
        owned = [actor for actor in actors.get_all_level_actors()
                 if actor.actor_has_tag("OasisLocal") or actor.actor_has_tag("OasisAuthored")]
        actors.destroy_actors(owned)
    elif not levels.new_level("/Game/Oasis/Maps/Oasis"):
        raise RuntimeError("Could not create owned world map")
    geo = actors.spawn_actor_from_class(unreal.CesiumGeoreference, unreal.Vector())
    geo.set_actor_label("WGS84 — Lujiazui origin")
    geo.set_editor_property("tags", ["OasisAuthored"])
    geo.set_origin_longitude_latitude_height(unreal.Vector(121.501909, 31.2364814, 0))
    raised = geo.transform_longitude_latitude_height_position_to_unreal(unreal.Vector(121.501909, 31.2364814, 1))
    if abs(raised.z - 100) > .01:
        raise RuntimeError("Georeference changed after compatibility fixes")
    manifest = json.loads((OUT / "exports/native-import/manifest.json").read_text())
    environment = json.loads((OUT / "exports/native-import/environment-manifest.json").read_text())
    packages = list(manifest["packages"]) + [{"chunk_id": "lujiazui_environment", "file": Path(environment["file"]).name,
                 "class": "environment", "sha256": environment["sha256"], "planned_cesium_esu_cm": [0, 0, 0]}]
    imported = []
    for package in packages:
        source = OUT / "exports/native-import" / package["file"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != package["sha256"]:
            raise RuntimeError("Audited FBX changed: " + package["file"])
        mesh = import_mesh(source, package["chunk_id"])
        slots = mesh.get_editor_property("static_materials")
        slot_names = []
        for index, slot in enumerate(slots):
            name = str(slot.get_editor_property("material_slot_name"))
            slot_names.append(name)
            matched = next((m for key, m in materials_by_name.items() if name.startswith(key)), materials_by_name["M_Mono_Building"])
            mesh.set_material(index, matched)
        body = mesh.get_editor_property("body_setup")
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        save(mesh)
        pivot = package["planned_cesium_esu_cm"]
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*pivot))
        actor.set_actor_label(package["chunk_id"])
        actor.set_editor_property("tags", ["OasisLocal", package["class"]])
        component = actor.static_mesh_component
        component.set_static_mesh(mesh)
        component.set_editor_property("render_custom_depth", True)
        component.set_editor_property("custom_depth_stencil_value", 1 if package["class"] == "hero" else 2 if package["class"] == "context" else 3)
        actor.set_actor_rotation(unreal.Rotator(0, basis["axis_import"]["root_yaw_correction_degrees"], 0), False)
        bounds = mesh.get_bounding_box()
        record = {"id": package["chunk_id"], "asset": mesh.get_path_name(), "actor_esu_cm": pivot,
                  "slots": slot_names, "height_cm": bounds.max.z - bounds.min.z,
                  "complex_collision": True}
        imported.append(record)
        unreal.log("OASIS_IMPORTED " + json.dumps(record))
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 150000))
    sun.set_actor_label("Soft monochrome sun")
    sun.set_editor_property("tags", ["OasisAuthored"])
    sun.set_actor_rotation(unreal.Rotator(-40, -150, 0), False)
    sun.light_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_intensity(4)
    sun.light_component.set_light_color(unreal.LinearColor(1, 1, 1, 1))
    sun.light_component.set_editor_property("light_source_angle", 4)
    fill = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 100000))
    fill.set_editor_property("tags", ["OasisAuthored"])
    fill.light_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    fill.light_component.set_intensity(.8)
    fill.light_component.set_editor_property("lower_hemisphere_is_black", True)
    fill.light_component.set_editor_property("lower_hemisphere_color", unreal.LinearColor(1, 1, 1, 1))
    volume = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector())
    volume.set_editor_property("tags", ["OasisAuthored"])
    volume.set_editor_property("unbound", True)
    settings = volume.get_editor_property("settings")
    blendable = unreal.WeightedBlendable()
    blendable.set_editor_property("weight", 1)
    blendable.set_editor_property("object", pp_material)
    weighted = unreal.WeightedBlendables()
    weighted.set_editor_property("array", [blendable])
    settings.set_editor_property("weighted_blendables", weighted)
    settings.set_editor_property("override_auto_exposure_method", True)
    settings.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    settings.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    settings.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    settings.set_editor_property("override_auto_exposure_bias", True)
    settings.set_editor_property("auto_exposure_bias", 0)
    settings.set_editor_property("override_motion_blur_amount", True)
    settings.set_editor_property("motion_blur_amount", 0)
    settings.set_editor_property("override_bloom_intensity", True)
    settings.set_editor_property("bloom_intensity", 0)
    volume.set_editor_property("settings", settings)
    world_actor = actors.spawn_actor_from_class(unreal.OasisWorld, unreal.Vector())
    world_actor.set_actor_label("Oasis continuous geospatial world")
    world_actor.set_editor_property("tags", ["OasisAuthored"])
    editor_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    editor_world.get_world_settings().set_editor_property("force_no_precomputed_lighting", True)
    unreal.EditorLevelLibrary.set_level_viewport_camera_info(unreal.Vector(-92000, 0, 70000), unreal.Rotator(-22.45, 0, 0))
    levels.save_current_level()
    assets.save_directory("/Game/Oasis", only_if_is_dirty=False, recursive=True)
    receipt.update(passed=True, imported=imported, imported_count=len(imported),
                   hero_height_cm={item["id"]: item["height_cm"] for item in imported if item["id"].startswith("hero")},
                   map="/Game/Oasis/Maps/Oasis", material_pipeline="Real native monochrome / stencil-depth-normal ink",
                   surveyed_ground_elevation=False, runtime_visual_qa_passed=False)
except Exception:
    receipt["error"] = traceback.format_exc()
    unreal.log_error(receipt["error"])
finally:
    if "levels" in globals():
        levels.save_current_level()
    (ROOT / "logs/native-scene-import.json").write_text(json.dumps(receipt, indent=2) + "\n")
    unreal.log("OASIS_SCENE_IMPORT=" + json.dumps({key: value for key, value in receipt.items() if key != "imported"}))
    unreal.SystemLibrary.quit_editor()

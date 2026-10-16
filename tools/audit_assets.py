"""Run inside Blender. Verify actual source geometry and FBX round-trip.

This checks interchange in Blender; UE import remains an independent gate.
"""
import json
import hashlib
import math
from pathlib import Path

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(json.loads((ROOT/'production-paths.json').read_text())['asset_root'])
manifest = json.loads((OUT/'exports/scene-manifest.json').read_text())
anchors = json.loads((ROOT/'geography/spatial-anchor-manifest.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(OUT/'source/lujiazui-hero-v1.blend'))
checks = []

def check(name, passed, evidence):
    checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})

def bounds(objects):
    pts = [obj.matrix_world@Vector(v) for obj in objects for v in obj.bound_box]
    return [[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]

hero_names = {
    'way.165792123': ['ShanghaiTower_Skin'],
    'way.376075961': ['JinMao_SteppedShaft','JinMao_Spire'],
    'way.10691100': ['SWFC_Envelope'],
}
source_summary = {}
for anchor in anchors['tower_anchors']:
    objects = [bpy.data.objects[n] for n in hero_names[anchor['entity_id']]]
    bb = bounds(objects)
    height = bb[2][1]-bb[2][0]
    delta = math.dist(list(objects[0].location)[:2],anchor['blender_enu_m'][:2])
    check(anchor['name']+' height', abs(height-anchor['height_m'])<.005,
          {'mesh_height_m':height,'expected_m':anchor['height_m'],'ground_height_unknown':True})
    check(anchor['name']+' anchor', delta<.001, {'horizontal_error_m':delta})
    for obj in objects:
        source_summary[obj.name] = {'location':list(obj.location),'bounds':bounds([obj]),'vertices':len(obj.data.vertices)}

sw = bpy.data.objects['SWFC_Envelope']
portal_hit = sw.ray_cast(Vector((-100,0,460)),Vector((1,0,0)))[0]
body_hit = sw.ray_cast(Vector((-100,0,420)),Vector((1,0,0)))[0]
check('SWFC actual through-opening',not portal_hit and body_hit,
      {'opening_center_ray_hits_mesh':portal_hit,'body_control_ray_hits_mesh':body_hit,'opening_dimensions_estimated':True})
asset_ids = [obj.get('entity_id') for obj in bpy.data.objects if obj.type=='MESH']
check('Unique mesh entity IDs',len(asset_ids)==len(set(asset_ids)) and None not in asset_ids,
      {'mesh_count':len(asset_ids),'unique_ids':len(set(asset_ids))})
finite = all(math.isfinite(c) for mesh in bpy.data.meshes for v in mesh.vertices for c in v.co)
check('Finite vertex coordinates',finite,{'meshes':len(bpy.data.meshes)})
bad_counts = []
for item in manifest['assets']:
    obj = bpy.data.objects.get(item['node_name'])
    if not obj or item['vertices']!=len(obj.data.vertices) or item['polygons']!=len(obj.data.polygons):
        bad_counts.append(item['node_name'])
check('Manifest counts match post-Boolean mesh',not bad_counts,{'mismatches':bad_counts})

bpy.context.view_layer.update()
shells = [bpy.data.objects[n] for names in hero_names.values() for n in names]
for view in ['C1','C2','C3','C4','C6','C7','HERO']:
    camera = bpy.data.objects['Camera_'+view]
    projected = [world_to_camera_view(bpy.context.scene,camera,obj.matrix_world@v.co)
                 for obj in shells for v in obj.data.vertices]
    extent = [[min(p[i] for p in projected),max(p[i] for p in projected)] for i in range(2)]
    check('Camera '+view+' trio frustum',all(0<=p.x<=1 and 0<=p.y<=1 and p.z>0 for p in projected),
          {'projected_xy_extent':extent,'scope':'Image-frame fit only; occlusion and native collision excluded'})

# This safely discards only in-memory scene data, never the saved source.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system='METRIC'
bpy.context.scene.unit_settings.scale_length=1
bpy.ops.import_scene.fbx(filepath=str(OUT/'exports/lujiazui-hero-v1.fbx'))
bpy.context.view_layer.update()
for name, expected in source_summary.items():
    obj = bpy.data.objects.get(name)
    if obj is None:
        check('FBX '+name,False,{'missing':True})
        continue
    bb = bounds([obj])
    max_error = max(abs(a-b) for axis_a,axis_b in zip(bb,expected['bounds']) for a,b in zip(axis_a,axis_b))
    check('FBX '+name, max_error<.02, {'max_world_bounds_error_m':max_error,'imported_vertices':len(obj.data.vertices)})
check('FBX custom entity IDs retained',all(bpy.data.objects[n].get('entity_id') for n in source_summary),{'hero_shells':list(source_summary)})
report = {'scope':'Blender source geometry and FBX round-trip only','checks':checks,
          'passed':all(c['passed'] for c in checks),'ue_import_verified':False,
          'source_blend_sha256':hashlib.sha256((OUT/'source/lujiazui-hero-v1.blend').read_bytes()).hexdigest(),
          'native_runtime_recorded':False,'source_ground_elevation_measured':False}
(OUT/'reviews/geometry-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
if not report['passed']:
    raise RuntimeError('Asset audit failed; inspect geometry-audit.json')

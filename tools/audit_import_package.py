"""Check every exported import chunk against its actual master geometry."""
import hashlib
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(json.loads((ROOT/'production-paths.json').read_text())['asset_root'])
DEST=OUT/'exports/native-import'
manifest=json.loads((DEST/'manifest.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(OUT/'source/lujiazui-hero-v1.blend'))
bpy.context.view_layer.update()
expected={}
for package in manifest['packages']:
    pivot=Vector(package['blender_pivot_enu_m'])
    points=[bpy.data.objects[m['source_node']].matrix_world@v.co-pivot
            for m in package['members'] for v in bpy.data.objects[m['source_node']].data.vertices]
    expected[package['chunk_id']]=[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]
checks=[]
for package in manifest['packages']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    file=DEST/package['file']
    bpy.ops.import_scene.fbx(filepath=str(file))
    bpy.context.view_layer.update()
    objects=[obj for obj in bpy.data.objects if obj.type=='MESH']
    points=[obj.matrix_world@v.co for obj in objects for v in obj.data.vertices]
    if not points:
        checks.append({'chunk_id':package['chunk_id'],'passed':False,'error':'empty geometry'})
        continue
    bb=[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]
    error=max(abs(a-b) for pairs in zip(bb,expected[package['chunk_id']]) for a,b in zip(*pairs))
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    id_ok=len(objects)==1 and objects[0].get('chunk_id')==package['chunk_id']
    finite=all(math.isfinite(c) for p in points for c in p)
    checks.append({'chunk_id':package['chunk_id'],'passed':error<.03 and digest==package['sha256'] and id_ok and finite,
                   'bounds_error_m':error,'chunk_id_retained':id_ok,'digest_verified':digest==package['sha256']})
report={'scope':'Blender FBX round-trip of every rebased package; UE import still pending',
        'passed':all(c['passed'] for c in checks),'checks':checks,'ue_import_verified':False,'native_fps_measured':False}
report['source_blend_sha256']=manifest['source_blend_sha256']
(OUT/'reviews/import-package-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':report['passed'],'chunks':len(checks),'failures':[c for c in checks if not c['passed']]}),flush=True)
if not report['passed']:raise RuntimeError('Import package failed audit')

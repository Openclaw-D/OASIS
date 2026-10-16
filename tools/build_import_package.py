"""Rebase and batch source assets for later Native import; no UE claims.

Preserves the master .blend. Hero towers remain separate; context is split into
250 m cells to reduce individual asset/actor overhead and permit spatial loading.
"""
import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(json.loads((ROOT/'production-paths.json').read_text())['asset_root'])
DEST=OUT/'exports/native-import'
DEST.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(OUT/'source/lujiazui-hero-v1.blend'))
bpy.context.view_layer.update()
source_objects=[obj for obj in bpy.data.objects if obj.type=='MESH']
groups={}
hero_names={'way.165792123':'ShanghaiTower','way.376075961':'JinMao','way.10691100':'SWFC'}
for obj in source_objects:
    entity=obj.get('entity_id','')
    hero=next((key for key in hero_names if entity.startswith(key+'.')),None)
    if hero:
        groups.setdefault('hero-'+hero_names[hero],[]).append(obj)
    elif obj.get('pw_class')=='building':
        pts=[obj.matrix_world@Vector(corner) for corner in obj.bound_box]
        center=[(min(p[i] for p in pts)+max(p[i] for p in pts))/2 for i in range(2)]
        tile=(math.floor(center[0]/250),math.floor(center[1]/250))
        region=obj.get('fidelity_region','context_buffer')
        groups.setdefault('context-%s-%d-%d'%(region,*tile),[]).append(obj)

packages=[]
for group_id,objects in sorted(groups.items()):
    objects=sorted(objects,key=lambda obj:obj.get('entity_id',''))
    is_hero=group_id.startswith('hero-')
    if is_hero:pivot=Vector(objects[0].location)
    else:
        first=objects[0]
        first_pts=[first.matrix_world@Vector(c) for c in first.bound_box]
        first_center=[(min(p[i] for p in first_pts)+max(p[i] for p in first_pts))/2 for i in range(2)]
        pivot=Vector([(math.floor(c/250)+.5)*250 for c in first_center]+[0])
    vertices=[];faces=[];material_indices=[];materials=[];material_map={};members=[]
    for obj in objects:
        start_v=len(vertices);start_f=len(faces)
        vertices.extend(tuple(obj.matrix_world@v.co-pivot) for v in obj.data.vertices)
        for polygon in obj.data.polygons:
            faces.append(tuple(start_v+i for i in polygon.vertices))
            mat=obj.data.materials[polygon.material_index]
            if mat.name not in material_map:
                material_map[mat.name]=len(materials);materials.append(mat)
            material_indices.append((material_map[mat.name],polygon.use_smooth))
        members.append({'entity_id':obj['entity_id'],'source_node':obj.name,
                        'source_vertex_range':[start_v,len(obj.data.vertices)],
                        'source_polygon_range':[start_f,len(obj.data.polygons)],
                        'provenance':obj.get('provenance')})
    mesh=bpy.data.meshes.new('PW_'+group_id)
    mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('PW_'+group_id,mesh);bpy.context.scene.collection.objects.link(obj)
    for mat in materials:mesh.materials.append(mat)
    for polygon,(idx,smooth) in zip(mesh.polygons,material_indices):
        polygon.material_index=idx;polygon.use_smooth=smooth
    obj['chunk_id']=group_id
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    fbx=DEST/(group_id+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},use_custom_props=True,
                             axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,bake_anim=False)
    packages.append({'chunk_id':group_id,'file':fbx.name,'class':'hero' if is_hero else 'context',
                      'blender_pivot_enu_m':list(pivot),'planned_cesium_esu_cm':[pivot.x*100,-pivot.y*100,pivot.z*100],
                      'mesh_vertices':len(vertices),'mesh_polygons':len(faces),'members':members,
                      'sha256':hashlib.sha256(fbx.read_bytes()).hexdigest(),'bytes':fbx.stat().st_size})
    bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)

report={'schema_version':1,'scope':'Rebased tower meshes and context batches for pending Native import',
        'source_blend_sha256':hashlib.sha256((OUT/'source/lujiazui-hero-v1.blend').read_bytes()).hexdigest(),
        'source_units':'meters','target_units':'centimeters after independently verified import',
        'context_cell_m':250,'hero_packages':sum(p['class']=='hero' for p in packages),
        'context_packages':sum(p['class']=='context' for p in packages),'source_context_objects':sum(len(p['members']) for p in packages if p['class']=='context'),
        'packages':packages,'ue_import_verified':False,'native_fps_measured':False,
        'basis_gate':'Planned ESU pivots are metadata only. Establish FBX local handedness/orientation with imported 1 m axis markers before placing actors.',
        'range_gate':'Member ranges refer to pre-export source polygons/vertices; FBX/UE may split/reorder them. They are not engine hit IDs.',
        'exclusions':['ground and terrain integration','walkable collision','trees/roads/parks','UI placement']}
(DEST/'manifest.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:report[k] for k in ['hero_packages','context_packages','source_context_objects','ue_import_verified','native_fps_measured']}),flush=True)

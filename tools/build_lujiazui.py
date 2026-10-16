"""Editable, geographically anchored architectural reconstruction.

Run in Blender background mode. Published overall heights and map anchors are
source-backed. All detailed facade/tier/opening dimensions are authored estimates.
This produces Native source assets and offline references, never a runtime demo.
"""
import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(json.loads((ROOT / 'production-paths.json').read_text())['asset_root'])
ANCHORS = json.loads((ROOT / 'geography/spatial-anchor-manifest.json').read_text())
TOKENS = json.loads((ROOT / 'workers/claude/design-tokens.json').read_text())
MAP = json.loads((ROOT.parent / 'data/lujiazui.geojson').read_text())
parser = argparse.ArgumentParser()
parser.add_argument('--render', default='C2')
parser.add_argument('--width', type=int, default=1920)
parser.add_argument('--samples', type=int, default=48)
parser.add_argument('--build-only', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'METAL'
prefs.get_devices()
for device in prefs.devices:
    device.use = device.type == 'METAL'
assert any(d.use for d in prefs.devices), 'Metal GPU missing'
scene.cycles.device = 'GPU'
scene.cycles.samples = args.samples
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = .025
scene.cycles.use_denoising = True
scene.render.resolution_x = args.width
scene.render.resolution_y = round(args.width * 9 / 16)
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0
scene.render.film_transparent = False

collections = {}
for name in ['HeroShells', 'HeroFacades', 'ContextBuildings', 'Ground', 'Roads', 'Nature', 'ScaleReferences', 'Cameras']:
    col = bpy.data.collections.new(name)
    scene.collection.children.link(col)
    collections[name] = col

def material(name, value, emission=0, roughness=1):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (value, value, value, 1)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value = (value, value, value, 1)
    node.inputs['Roughness'].default_value = roughness
    node.inputs['Specular IOR Level'].default_value = .06
    node.inputs['Emission Color'].default_value = (1, 1, 1, 1)
    node.inputs['Emission Strength'].default_value = emission
    return mat

hero_mat = material('M_Mono_Hero', .90)
context_mat = material('M_Mono_Building', .91, .05)
ground_mat = material('M_Mono_Ground', .96, .04)
water_mat = material('M_Mono_Water', .85, .03)
detail_mat = material('M_Mono_Detail', .16)
ink_mat = material('M_Mono_Ink', .003)
road_mat = material('M_Mono_Road', .86, .03)
nature_mat = material('M_Mono_Nature', .85, .03)

world = bpy.data.worlds.new('WhitePaperWorld')
world.use_nodes = True
wn = world.node_tree.nodes
wn.clear()
wout = wn.new('ShaderNodeOutputWorld')
fill = wn.new('ShaderNodeBackground')
fill.inputs['Color'].default_value = (1, 1, 1, 1)
fill.inputs['Strength'].default_value = .70
camera_bg = wn.new('ShaderNodeBackground')
camera_bg.inputs['Color'].default_value = (1, 1, 1, 1)
camera_bg.inputs['Strength'].default_value = 1
path = wn.new('ShaderNodeLightPath')
mix = wn.new('ShaderNodeMixShader')
wl = world.node_tree.links
wl.new(path.outputs['Is Camera Ray'], mix.inputs[0])
wl.new(fill.outputs[0], mix.inputs[1])
wl.new(camera_bg.outputs[0], mix.inputs[2])
wl.new(mix.outputs[0], wout.inputs[0])
scene.world = world

records = []
def mesh_object(name, vertices, faces, mat, col, entity_id, provenance, smooth=False):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collections[col].objects.link(obj)
    obj.data.materials.append(mat)
    if smooth:
        for poly in mesh.polygons: poly.use_smooth = True
    obj['entity_id'] = entity_id
    obj['asset_version'] = 1
    obj['pw_class'] = 'hero' if col.startswith('Hero') else 'building' if col == 'ContextBuildings' else 'ground'
    obj['provenance'] = provenance
    records.append({'entity_id': entity_id, 'node_name': name, 'asset_version': 1,
                    'class': obj['pw_class'], 'provenance': provenance,
                    'material_ids': [mat.name], 'vertices': len(vertices), 'polygons': len(faces)})
    return obj

def loft(name, rings, mat, col, entity_id, provenance, smooth=False):
    n = len(rings[0]); vertices = [v for ring in rings for v in ring]
    faces = [tuple(reversed(range(n))), tuple(range((len(rings)-1)*n, len(rings)*n))]
    for k in range(len(rings)-1):
        for i in range(n):
            j = (i+1) % n
            faces.append((k*n+i, k*n+j, (k+1)*n+j, (k+1)*n+i))
    return mesh_object(name, vertices, faces, mat, col, entity_id, provenance, smooth)

def tubes(name, paths, radius, mat, col, entity_id, provenance):
    vertices, faces = [], []
    for points in paths:
        if len(points) < 2: continue
        start = len(vertices)
        for i, p in enumerate(points):
            p = Vector(p)
            tangent = Vector(points[min(i+1, len(points)-1)]) - Vector(points[max(i-1, 0)])
            if tangent.length < 1e-8: tangent = Vector((0, 0, 1))
            tangent.normalize()
            ref = Vector((0, 0, 1)) if abs(tangent.z) < .9 else Vector((1, 0, 0))
            u = tangent.cross(ref).normalized() * radius
            v = tangent.cross(u).normalized() * radius
            for j in range(4):
                vertices.append(tuple(p + u*math.cos(j*math.pi/2) + v*math.sin(j*math.pi/2)))
        for i in range(len(points)-1):
            for j in range(4):
                a=start+i*4+j; b=start+i*4+(j+1)%4
                faces.append((a, b, b+4, a+4))
    return mesh_object(name, vertices, faces, mat, col, entity_id, provenance)

def xy(lon_lat):
    # Exact WGS84 ECEF-to-ENU horizontal coordinates at reference height zero.
    # Ground heights are unknown; a flat authoring surface remains an estimate.
    lon0, lat0 = ANCHORS['origin_wgs84_lon_lat']
    a = 6378137.; e2 = .0066943799901413165
    def ecef(lon, lat):
        lon, lat = math.radians(lon), math.radians(lat)
        n = a / math.sqrt(1-e2*math.sin(lat)**2)
        return (n*math.cos(lat)*math.cos(lon), n*math.cos(lat)*math.sin(lon), n*(1-e2)*math.sin(lat))
    delta = [p-o for p,o in zip(ecef(*lon_lat), ecef(lon0,lat0))]
    lon,lat = math.radians(lon0),math.radians(lat0)
    return (-math.sin(lon)*delta[0] + math.cos(lon)*delta[1],
            -math.sin(lat)*math.cos(lon)*delta[0] - math.sin(lat)*math.sin(lon)*delta[1] + math.cos(lat)*delta[2])

anchors = {a['entity_id']: a for a in ANCHORS['tower_anchors']}
def place(obj, anchor): obj.location = (*anchor['blender_enu_m'][:2], 0)

st = anchors['way.165792123']
def st_point(t, angle, offset=0):
    # The primary paper shows one re-entrant notch in the cam-shaped profile.
    # This authored polar approximation is not the architect's exact arc model.
    wrapped = abs((angle-3.7+math.pi) % math.tau-math.pi)
    notch = max(0, 1-wrapped/.13) * 4.0
    radius = (46*(1+.105*math.cos(3*angle)+.055*math.cos(angle-.7))-notch)*.45**t + offset
    theta = angle + math.radians(-18 + 120*t)
    cap = max(0, (t-.96)/.04)**2
    return (radius*math.cos(theta), radius*math.sin(theta), 632*t + (9*math.cos(angle)-9)*cap)

st_rings = [[st_point(k/140, i*math.tau/120) for i in range(120)] for k in range(141)]
obj = loft('ShanghaiTower_Skin', st_rings, hero_mat, 'HeroShells', 'way.165792123.skin',
           'Published height 632 m / 120 degree twist / approximately 55 percent reduction; authored rounded-triangle profile and crown', True)
place(obj, st)
paths = [[st_point(k/140, i*math.tau/96, .14) for k in range(141)] for i in range(96)]
paths += [[st_point(k/130, i*math.tau/120, .16) for i in range(121)] for k in range(1,127)]
obj=tubes('ShanghaiTower_Mullions', paths, .10, detail_mat, 'HeroFacades', 'way.165792123.facade', 'Authored facade subdivision estimate')
place(obj, st)
seams=[[st_point(k/160, 3.7, .24) for k in range(161)]]
obj=tubes('ShanghaiTower_SpiralNotch', seams, .22, ink_mat, 'HeroFacades', 'way.165792123.seams', 'Single notch informed by Gensler design-paper figure 3; authored depth and orientation')
place(obj, st)

jm = anchors['way.376075961']
floors=[16,14,12,10,8,7,6,5,4,3,3]
profile=[(0,32)]; z=0
for i,count in enumerate(floors):
    r=32*.885**i; z+=count*365/88
    profile += [(z-1.1,r),(z,r+1.3),(z+.8,r+1.3),(z+1.6,32*.885**(i+1))]
profile += [(372,8.6),(379,9.2),(380,7.8),(389,7.8),(390,6.2),(399,4.8),(407,2.4)]
profile=sorted(profile, key=lambda p:p[0])
def jm_ring(z,r):
    # Stepped outer corners; the documented structural core is octagonal.
    # These outer facade dimensions are a reconstruction estimate.
    quadrant=[(r,0),(r,.44*r),(.82*r,.44*r),(.82*r,.82*r),(.44*r,.82*r),(.44*r,r)]
    return [(x*math.cos(q*math.pi/2)-y*math.sin(q*math.pi/2),
             x*math.sin(q*math.pi/2)+y*math.cos(q*math.pi/2),z)
            for q in range(4) for x,y in quadrant]
obj=loft('JinMao_SteppedShaft', [jm_ring(z,r) for z,r in profile],hero_mat,'HeroShells','way.376075961.shaft',
         'Published 420.5 m / 88 stories / pagoda-inspired setbacks; authored tier elevations, radii and crown')
place(obj,jm)
obj=loft('JinMao_Spire',[jm_ring(407,1.8),jm_ring(417,.65),jm_ring(420.5,.08)],detail_mat,'HeroShells','way.376075961.spire','Authored spire; combined overall height fixed to 420.5 m')
place(obj,jm)
jm_paths=[]
for z,r in profile[1:]: jm_paths.append(jm_ring(z,r+.12)+[jm_ring(z,r+.12)[0]])
for i in range(24):
    for f in [.30,.70]:
        path=[]
        for z,r in profile:
            ring=jm_ring(z,r+.1); a=Vector(ring[i]); b=Vector(ring[(i+1)%24]); path.append(tuple(a.lerp(b,f)))
        jm_paths.append(path)
obj=tubes('JinMao_Fins',jm_paths,.105,detail_mat,'HeroFacades','way.376075961.fins','Authored mullions and terrace rails')
place(obj,jm)

sw = anchors['way.10691100']
def sw_ring(z):
    # Broad portal facade faces east/west; base axes follow the mapped footprint.
    # Taper and aperture dimensions/orientation remain authored estimates.
    t=z/492; wx=33*(1-.82*t*t); wy=33*(1-.16*t)
    return [(-wx,-wy,z),(wx,-wy,z),(wx,wy,z),(-wx,wy,z)]
obj=loft('SWFC_Envelope',[sw_ring(z) for z in sorted(set([k*492/64 for k in range(65)]+[447,483]))],hero_mat,'HeroShells','way.10691100.envelope',
         'Published 492 m / 101 floors and square-prism/arc/sky-portal form; authored taper and opening dimensions')
cutter_verts=[(-15.5,-60,447),(15.5,-60,447),(19.5,-60,483),(-19.5,-60,483),(-15.5,60,447),(15.5,60,447),(19.5,60,483),(-19.5,60,483)]
cutter_verts=[(y,-x,z) for x,y,z in cutter_verts]
cutter=mesh_object('SWFC_OpeningCutter',cutter_verts,[(1,2,3,0),(7,6,5,4),(4,5,1,0),(5,6,2,1),(6,7,3,2),(7,4,0,3)],hero_mat,'HeroShells','temporary.swfc.cut','Temporary authored boolean cutter')
bpy.context.view_layer.objects.active=obj; obj.select_set(True)
mod=obj.modifiers.new('OpenSkyPortal','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(cutter,do_unlink=True)
records[:]=[r for r in records if r['entity_id']!='temporary.swfc.cut']
place(obj,sw);obj.rotation_euler.z=math.radians(6)
sw_paths=[]
for k in range(1,101):
    z=k*492/103; ring=sw_ring(z)
    if 447<z<483:
        half=15.5+(z-447)/36*4
        for sign in [-1,1]:
            for x in [ring[0][0]-.12,ring[1][0]+.12]:
                sw_paths.append([(x,sign*half,z),(x,sign*abs(ring[0][1]),z)])
    else: sw_paths.append([(x+(.13 if x>0 else -.13),y,z) for x,y,z in ring]+[(ring[0][0]-.13,ring[0][1],z)])
for k in range(21):
    f=-1+2*k/20
    for sign in [-1,1]:
        path=[]
        for z in range(0,493,3):
            ring=sw_ring(z); y=abs(ring[0][1])*f; x=sign*(abs(ring[0][0])+.13)
            if 447<z<483 and abs(y)<15.5+(z-447)/36*4:
                if len(path)>1:sw_paths.append(path)
                path=[]
            else:path.append((x,y,z))
        if len(path)>1:sw_paths.append(path)
# The narrow north/south side faces need their own continuous mullions.
for k in range(11):
    f=-1+2*k/10
    for sign in [-1,1]:
        sw_paths.append([(abs(sw_ring(z)[0][0])*f,sign*(abs(sw_ring(z)[0][1])+.13),z)
                         for z in range(0,493,3)])
obj=tubes('SWFC_CurtainGrid',sw_paths,.105,detail_mat,'HeroFacades','way.10691100.grid','Authored curtain-wall subdivision, respects real mesh opening')
place(obj,sw);obj.rotation_euler.z=math.radians(6)
edge_paths=[[tuple(Vector(sw_ring(z)[corner])+Vector((.10 if corner in [1,2] else -.10,
                                                              .10 if corner in [2,3] else -.10,0)))
             for z in [k*492/128 for k in range(129)]] for corner in range(4)]
obj=tubes('SWFC_ExpressiveEdgeRibs',edge_paths,.38,ink_mat,'HeroFacades','way.10691100.ribs',
          'Authored graphic corner-edge ribs for continuous ink; width is an expressive reconstruction estimate, not an as-built measurement')
place(obj,sw);obj.rotation_euler.z=math.radians(6)

def polygon_obj(name,points,z,height,mat,col,entity,provenance):
    points=[tuple(p) for p in points]
    if points[0]==points[-1]:points=points[:-1]
    clean=[]
    for p in points:
        if not clean or math.dist(clean[-1],p)>.01:clean.append(p)
    if len(clean)<3:return None
    area=sum(clean[i][0]*clean[(i+1)%len(clean)][1]-clean[(i+1)%len(clean)][0]*clean[i][1] for i in range(len(clean)))
    if area<0:clean.reverse()
    rings=[[(x,y,z) for x,y in clean],[(x,y,z+height) for x,y in clean]]
    return loft(name,rings,mat,col,entity,provenance)

mesh_object('WhiteGround',[(-6500,-6500,-.3),(6500,-6500,-.3),(6500,6500,-.3),(-6500,6500,-.3)],[(0,1,2,3)],ground_mat,'Ground','ground.base','Flat reference ground; elevation unknown')
hero_ids={'way/165792123','way/376075961','way/10691100'}
context_counts={'map_height':0,'level_estimate':0,'authored_estimate':0,'target':0,'buffer':0}
green_polygons=[]; road_paths=[]
for feature in MAP['features']:
    p=feature['properties']; kind=p['kind']; geom=feature['geometry']; osm=p['osm_id']; entity=osm.replace('/','.')
    if kind in ['venue','station']:continue
    coords=geom['coordinates'][0] if geom['type']=='Polygon' else geom['coordinates']
    points=[xy(c) for c in coords]
    if not points:continue
    cx=(min(x for x,y in points)+max(x for x,y in points))/2
    cy=(min(y for x,y in points)+max(y for x,y in points))/2
    dist=math.hypot(cx,cy)
    if kind!='water' and dist>1250:continue
    if kind=='building' and osm not in hero_ids:
        h=p.get('height_m')
        if h:
            provenance='OSM-tagged height; not surveyed';context_counts['map_height']+=1
        else:
            try:levels=float(p.get('building:levels') or 0)
            except (TypeError,ValueError):levels=0
            if levels>0:h=levels*3.8+1.5;provenance='Estimated from OSM floor count, authored 3.8 m spacing';context_counts['level_estimate']+=1
            else:
                # Background masses only; no fabricated measurements.
                area=abs(sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points)))/2)
                h=12 if area<160 else 22 if area<900 else 34
                provenance='Authored context height estimate; source height missing';context_counts['authored_estimate']+=1
        target=dist<=1000
        context_counts['target' if target else 'buffer']+=1
        obj=polygon_obj('Building_'+entity.replace('.','_'),points,0,h,context_mat,'ContextBuildings',entity,provenance)
        if obj:obj['fidelity_region']='target' if target else 'context_buffer'
    elif kind=='water':polygon_obj('Water_'+entity.replace('.','_'),points,-.15,.05,water_mat,'Ground',entity,'OSM water boundary; flat authored surface')
    elif kind=='green':
        polygon_obj('Park_'+entity.replace('.','_'),points,-.02,.05,nature_mat,'Nature',entity,'OSM green footprint; authored surface')
        if dist<1050:green_polygons.append(points)
    elif kind=='road':
        road_paths.append([(x,y,.045) for x,y in points])
tubes('RoadCenterInks',road_paths,.32,road_mat,'Roads','roads.vector_network','OSM mapped street centerlines; stylized reference strokes, not surveyed road widths')

def inside(point,polygon):
    x,y=point; result=False;j=len(polygon)-1
    for i,(xi,yi) in enumerate(polygon):
        xj,yj=polygon[j]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/(yj-yi)+xi:result=not result
        j=i
    return result
tree_vertices=[];tree_faces=[];rng=random.Random(20261005)
for poly in green_polygons:
    xmin,xmax=min(x for x,y in poly),max(x for x,y in poly)
    ymin,ymax=min(y for x,y in poly),max(y for x,y in poly)
    for x in range(math.ceil(xmin/24)*24,math.floor(xmax/24)*24+1,24):
        for y in range(math.ceil(ymin/24)*24,math.floor(ymax/24)*24+1,24):
            x1,y1=x+rng.uniform(-4,4),y+rng.uniform(-4,4)
            if not inside((x1,y1),poly):continue
            h=rng.uniform(4.5,8.5);r=h*.30;start=len(tree_vertices)
            for z,rad in [(h*.28,r*.65),(h*.65,r),(h,r*.04)]:
                tree_vertices.extend([(x1+rad*math.cos(i*math.tau/8),y1+rad*math.sin(i*math.tau/8),z) for i in range(8)])
            for k in range(2):
                for i in range(8):tree_faces.append((start+k*8+i,start+k*8+(i+1)%8,start+(k+1)*8+(i+1)%8,start+(k+1)*8+i))
mesh_object('ParkTrees',tree_vertices,tree_faces,nature_mat,'Nature','nature.authored_trees','Synthetic park planting estimate, not individually mapped trees',True)

sun_data=bpy.data.lights.new('SoftSun','SUN');sun_data.energy=1.45;sun_data.angle=math.radians(4)
sun=bpy.data.objects.new('SoftSun',sun_data);scene.collection.objects.link(sun)
az,el=math.radians(240),math.radians(40)
direction=Vector((math.sin(az)*math.cos(el),math.cos(az)*math.cos(el),math.sin(el)))
sun.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()

camera_manifest=[]
for key,pose in TOKENS['camera']['poses']['presets'].items():
    data=bpy.data.cameras.new('Camera_'+key);data.lens=pose['lensMm'];data.sensor_width=36;data.sensor_fit='HORIZONTAL'
    obj=bpy.data.objects.new('Camera_'+key,data);collections['Cameras'].objects.link(obj)
    obj.location=pose['enu'];target=Vector(pose['targetEnu'])
    obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
    data.clip_start=.1;data.clip_end=20000
    camera_manifest.append({'id':key,'pos_enu_m':pose['enu'],'target_enu_m':pose['targetEnu'],'lens_mm':pose['lensMm'],'sensor_mm':[36,20.25],'ground_elevation_status':'unknown; reference zero'})
data=bpy.data.cameras.new('Camera_HERO');data.type='ORTHO';data.ortho_scale=1550
obj=bpy.data.objects.new('Camera_HERO',data);collections['Cameras'].objects.link(obj)
obj.location=(1050,-1250,1150);target=Vector((0,0,240));obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
data.clip_end=20000
camera_manifest.append({'id':'HERO','pos_enu_m':list(obj.location),'target_enu_m':list(target),'projection':'ORTHO','ortho_width_m':1550,'scope':'Offline architectural overview'})
data=bpy.data.cameras.new('Camera_C6');data.lens=35;data.sensor_width=36;data.sensor_fit='HORIZONTAL'
obj=bpy.data.objects.new('Camera_C6',data);collections['Cameras'].objects.link(obj)
obj.location=(-1490,-130,160);target=Vector((0,0,300));obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
data.clip_end=20000
camera_manifest.append({'id':'C6','pos_enu_m':list(obj.location),'target_enu_m':list(target),'lens_mm':35,'sensor_mm':[36,20.25],'scope':'Authored hero still; walkability and missing distant context unresolved'})
data=bpy.data.cameras.new('Camera_C7');data.lens=27;data.sensor_width=36;data.sensor_fit='HORIZONTAL'
obj=bpy.data.objects.new('Camera_C7',data);collections['Cameras'].objects.link(obj)
obj.location=(-920,0,700);target=Vector((0,0,320));obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
data.clip_end=20000
camera_manifest.append({'id':'C7','pos_enu_m':list(obj.location),'target_enu_m':list(target),'lens_mm':27,'sensor_mm':[36,20.25],'scope':'Raised west-side three-tower composition; authored estimate'})
scene.camera=bpy.data.objects['Camera_'+args.render]

scene.render.use_freestyle=True
# A separate ink layer prevents thin facade tubes from cutting silhouette chains.
# Beauty retains all facade geometry. This is an offline reference pipeline;
# the eventual UE stencil/depth route needs its own temporal validation.
beauty=scene.view_layers[0];beauty.name='Beauty';beauty.use_freestyle=False
ink=scene.view_layers.new('Ink');ink.samples=1;ink.use_freestyle=True
for layer in ink.layer_collection.children:
    if layer.name in ['HeroFacades','Nature','Roads']:layer.exclude=True
settings=ink.freestyle_settings;settings.as_render_pass=True
settings.crease_angle=math.radians(140)
while len(settings.linesets):settings.linesets.remove(settings.linesets[0])
scene.render.line_thickness_mode='ABSOLUTE'
for name,col,color,thickness in [('HeroContours','HeroShells',.003,2.2),('ContextContours','ContextBuildings',.30,.95)]:
    line=settings.linesets.new(name);line.select_by_collection=True;line.collection=collections[col]
    line.select_silhouette=True;line.select_border=True;line.select_crease=True;line.select_edge_mark=False
    line.linestyle.caps='ROUND'
    line.linestyle.color=(color,color,color);line.linestyle.thickness=thickness*scene.render.resolution_y/1440

group=bpy.data.node_groups.new('ArchitectureInkComposite','CompositorNodeTree')
group.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
scene.compositing_node_group=group
beauty_node=group.nodes.new('CompositorNodeRLayers');beauty_node.layer='Beauty'
ink_node=group.nodes.new('CompositorNodeRLayers');ink_node.layer='Ink'
over=group.nodes.new('CompositorNodeAlphaOver');over.inputs['Factor'].default_value=1
output=group.nodes.new('NodeGroupOutput')
group.links.new(beauty_node.outputs['Image'],over.inputs['Background'])
group.links.new(ink_node.outputs['Freestyle'],over.inputs['Foreground'])
group.links.new(over.outputs['Image'],output.inputs['Image'])

for item in records:
    obj=bpy.data.objects.get(item['node_name'])
    if obj:
        item['vertices'] = len(obj.data.vertices)
        item['polygons'] = len(obj.data.polygons)
        item['pose_m']={'position':list(obj.location),'rotation_euler_rad':list(obj.rotation_euler),'scale':list(obj.scale)}
        item['asset_id']=item['entity_id']+'.v1'
        item['asset_source']=str(OUT/'source/lujiazui-hero-v1.blend')
        item['interchange_source']=str(OUT/'exports/lujiazui-hero-v1.fbx')
manifest={'schema_version':1,'origin':ANCHORS['origin_wgs84_lon_lat'],'coordinate_frame':'Blender ENU meters; UE ESU centimeters','radius_m':1000,'context_buffer_m':1250,'ground_elevation_status':'unknown; flat reference zero','assets':records,'cameras':camera_manifest,'context_counts':context_counts,'provenance_policy':'Architectural reconstruction. Published total heights and map anchors; detailed dimensions, context heights and planting retain estimates. No surveyed mesh or verified interiors.','ue_import_verified':False,'native_runtime_recorded':False}
(OUT/'exports/scene-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
scene.render.filepath=str(OUT/'renders'/('reference-'+args.render+'.png'))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'source/lujiazui-hero-v1.blend'))
bpy.ops.export_scene.fbx(filepath=str(OUT/'exports/lujiazui-hero-v1.fbx'),object_types={'EMPTY','MESH'},use_custom_props=True,axis_forward='-Y',axis_up='Z',global_scale=1.0,use_mesh_modifiers=True,apply_unit_scale=True,bake_anim=False)
report={'scope':'Blender asset authoring and offline reference, not Native runtime','objects':len(bpy.data.objects),'mesh_vertices':sum(len(m.vertices) for m in bpy.data.meshes),'mesh_polygons':sum(len(m.polygons) for m in bpy.data.meshes),'context_counts':context_counts,'build_seconds':round(time.perf_counter()-started,3),'blend':str(OUT/'source/lujiazui-hero-v1.blend'),'fbx':str(OUT/'exports/lujiazui-hero-v1.fbx'),'render_requested':not args.build_only,'render_view':args.render,'gpu':'Metal'}
(OUT/'logs/build-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
if not args.build_only:
    bpy.ops.render.render(write_still=True)
    report['render_exists']=Path(scene.render.filepath).exists();report['total_seconds']=round(time.perf_counter()-started,3)
    (OUT/'logs/build-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)

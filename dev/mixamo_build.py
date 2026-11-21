"""
dev/mixamo_build.py - TEST (21 Nov): Jay's Mixamo footballer and moves -> broadcast3d/models/mixamo_footballer.glb

Runs in Blender's Python (pip "bpy", Python 3.11):   python3.11 dev/mixamo_build.py <Soccer Game Pack folder> <out.glb>
  - the footballer (Ch38_nonPBR.fbx) and each move (downloaded "Without Skin")
  - the running moves are made to run on the spot (the travel taken out of the hips - the match engine moves him);
    how far each travelled is written to the .json, so the viewer can play each at the pace that matches his speed
  - pictures shrunk to 1024 (plenty at TV distance)
"""
import bpy, sys, os, json
U = sys.argv[-2]
OUT = sys.argv[-1]
names = ["offensive idle", "Idle", "Idle (1)", "Breathing Idle", "jog forward", "Standard Run", "Sprint", "Left Strafe",
         "Right Strafe", "Running Backward", "kick soccerball", "Victory"]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=f"{U}/Ch38_nonPBR.fbx")
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
arm.animation_data_create()
info = {}
MOVING = ("jog forward", "Standard Run", "Sprint", "Left Strafe", "Right Strafe", "Running Backward")
for n in names:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=f"{U}/{n}.fbx")
    new = [o for o in bpy.context.scene.objects if o not in before]
    a2 = next(o for o in new if o.type == "ARMATURE")
    act = a2.animation_data.action
    nm = n.replace(" ", "_").replace("(", "").replace(")", "")
    act.name = nm
    act.use_fake_user = True
    drift = {}
    # In place: take the travel out of the hips (keep the bob and sway) - the engine moves him
    fcs = [fc for fc in (act.fcurves if hasattr(act, "fcurves") else []) ]
    if not fcs:
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs += list(cb.fcurves)
    for fc in fcs:
        if fc.data_path.endswith('"].location') and "Hips" in fc.data_path:
            kp = fc.keyframe_points
            if len(kp) < 2:
                continue
            f0, v0 = kp[0].co[0], kp[0].co[1]
            f1, v1 = kp[-1].co[0], kp[-1].co[1]
            d = v1 - v0
            drift[fc.array_index] = d
            if abs(d) > 1.0 and n in MOVING:
                for k in kp:
                    t = (k.co[0] - f0) / max(1e-6, f1 - f0)
                    k.co[1] -= d * t
                    k.handle_left[1] -= d * t
                    k.handle_right[1] -= d * t
    info[nm] = {"frames": list(act.frame_range), "drift": drift}
    track = arm.animation_data.nla_tracks.new(); track.name = nm
    track.strips.new(nm, int(act.frame_range[0]), act)
    track.mute = True
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    print("ACT", nm, act.frame_range[:], drift)
# Lighter pictures: 1024 is plenty at TV distance
for im in bpy.data.images:
    if im.size[0] > 1024:
        im.scale(1024, 1024)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_animations=True, export_animation_mode="NLA_TRACKS",
                          export_image_format="JPEG", export_jpeg_quality=88)
json.dump(info, open(OUT.replace(".glb", ".json"), "w"), indent=1)
print("WROTE", OUT, os.path.getsize(OUT))

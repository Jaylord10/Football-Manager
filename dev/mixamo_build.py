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
# Moves with the ball, played straight from the motion capture: the frame of the moment (the ball struck, headed,
# let go) - found from the joints' paths (the foot passing the ball's height on its way through, the head at its
# furthest forward, the hands at their fastest).  These are put on the spot at that moment: the engine has him there.
ACTION = {"kick soccerball (2)": 5, "strike foward jog": 12, "Chip": 14, "header soccerball": 22, "throw in": 47,
          "goalkeeper overhand throw": 47, "goalkeeper drop kick": 62}
names += list(ACTION)
# Right-footed moves also made left-footed: every frame mirrored, left to right (each bone takes its opposite
# number's pose, reflected across the middle of him) - saved as "<move>_M"
MIRROR = ("kick soccerball (2)", "strike foward jog", "Chip")


def mirrored(arm, act, nm):
    """A copy of act played the other way round (left <-> right)."""
    from mathutils import Matrix
    S = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    sc = bpy.context.scene
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    arm.animation_data.action = act
    pbs = sorted(arm.pose.bones, key=lambda b: len(b.parent_recursive))
    other = lambda n: n.replace("Left", "@").replace("Right", "Left").replace("@", "Right")
    mats = {}
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        mats[f] = {b.name: b.matrix.copy() for b in pbs}
    arm.animation_data.action = None
    am = bpy.data.actions.new(nm)
    am.use_fake_user = True
    arm.animation_data.action = am
    for f in range(f0, f1 + 1):
        for b in pbs:
            src = other(b.name) if other(b.name) in mats[f] else b.name
            b.matrix = S @ mats[f][src] @ S
            bpy.context.view_layer.update()
            b.keyframe_insert("rotation_quaternion", frame=f)
            b.keyframe_insert("location", frame=f)
    arm.animation_data.action = None
    for b in pbs:                                                   # (back to his rest pose)
        b.rotation_quaternion = (1, 0, 0, 0); b.location = (0, 0, 0)
    return am
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
        if n in ACTION and fc.data_path.endswith('"].location') and "Hips" in fc.data_path and fc.array_index in (0, 2):
            at = fc.evaluate(act.frame_range[0] + ACTION[n])      # (no travel, across or forward: held where he
            for k in fc.keyframe_points:                          #  is at the moment)
                k.co[1] = at; k.handle_left[1] = at; k.handle_right[1] = at
            drift[fc.array_index] = 0.0
            continue
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
    if n in ACTION:
        info[nm]["moment"] = ACTION[n]
    track = arm.animation_data.nla_tracks.new(); track.name = nm
    track.strips.new(nm, int(act.frame_range[0]), act)
    track.mute = True
    if n in MIRROR:
        am = mirrored(arm, act, nm + "_M")
        tm = arm.animation_data.nla_tracks.new(); tm.name = nm + "_M"
        tm.strips.new(nm + "_M", int(am.frame_range[0]), am)
        tm.mute = True
        info[nm + "_M"] = dict(info[nm])
        print("MIRRORED", nm)
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

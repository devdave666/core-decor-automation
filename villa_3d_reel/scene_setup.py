"""
Headless Blender (bpy) scene blockout for the "3D-to-AI-video" test pipeline.

Builds a rough primitive-mesh blockout of a Mediterranean villa terrace
(columns, patio walls, pool, lounge chairs) purely as a composition/lighting
reference for Veo's image-conditioning input -- it is not meant to look
finished, just to pin down camera framing and layout before the expensive
photoreal generation step (generate_veo.py) runs.

Run with the pip-installed `bpy` module (no Blender application needed):
    villa_3d_reel/.venv313/Scripts/python.exe villa_3d_reel/scene_setup.py

Outputs (into villa_3d_reel/output/):
    reference_frame.png   -- frame 1, BLENDER_WORKBENCH solid+cavity+outline
    blockout.mp4          -- optional 5s/24fps playblast of the push-in/pan
"""
import math
import subprocess
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
OUT.mkdir(exist_ok=True)

RENDER_VIDEO = "--video" in sys.argv

WIDTH, HEIGHT = 1080, 1920
FPS = 24
DURATION_S = 5
END_FRAME = FPS * DURATION_S  # 120


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def add_box(name, location, scale, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    return obj


def add_plane(name, location, scale, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = rotation
    return obj


def build_villa_terrace():
    # Floor: travertine patio slab.
    add_plane("PatioFloor", (0, 4, 0), (6, 6, 1))

    # Infinity pool: recessed plane, slightly below floor level, blue-tinted
    # via viewport display color (workbench shading reads object color).
    pool = add_plane("Pool_Water", (0, 10, -0.05), (4.5, 3, 1))
    pool.color = (0.05, 0.35, 0.55, 1.0)

    # Ocean backdrop: large plane far behind, angled up to fill horizon.
    ocean = add_plane("Ocean_Backdrop", (0, 40, 3), (25, 1, 15), rotation=(math.radians(90), 0, 0))
    ocean.color = (0.02, 0.25, 0.45, 1.0)

    # Sky backdrop, higher and lighter.
    sky = add_plane("Sky_Backdrop", (0, 60, 20), (30, 1, 20), rotation=(math.radians(90), 0, 0))
    sky.color = (0.6, 0.8, 0.95, 1.0)

    # Colonnade: row of columns framing the terrace on both sides.
    col_positions = [-5, -3, 3, 5]
    for i, x in enumerate(col_positions):
        col = add_box(f"Column_{i}", (x, 1, 1.5), (0.3, 0.3, 1.5))
        col.color = (0.85, 0.8, 0.7, 1.0)

    # Low patio walls at the pool edge (infinity-edge suggestion).
    wall_l = add_box("PatioWall_L", (-6, 4, 0.5), (0.2, 6, 0.5))
    wall_r = add_box("PatioWall_R", (6, 4, 0.5), (0.2, 6, 0.5))
    for w in (wall_l, wall_r):
        w.color = (0.8, 0.75, 0.65, 1.0)

    pool_edge = add_box("Pool_InfinityEdge", (0, 13, 0.1), (4.5, 0.2, 0.15))
    pool_edge.color = (0.75, 0.7, 0.6, 1.0)

    # Lounge chairs: simple low blockout (seat + backrest) x2.
    for i, x in enumerate([-2.2, 2.2]):
        seat = add_box(f"Lounge_Seat_{i}", (x, 5.5, 0.3), (0.6, 1.4, 0.15))
        back = add_box(f"Lounge_Back_{i}", (x, 6.8, 0.7), (0.6, 0.15, 0.5), rotation=(math.radians(-20), 0, 0))
        for o in (seat, back):
            o.color = (0.9, 0.9, 0.85, 1.0)

    # Dining table blockout.
    table_top = add_box("DiningTable_Top", (0, 2, 1.0), (1.2, 0.7, 0.05))
    table_leg = add_box("DiningTable_Leg", (0, 2, 0.5), (0.1, 0.1, 0.5))
    for o in (table_top, table_leg):
        o.color = (0.55, 0.4, 0.25, 1.0)


def set_object_color_display():
    """Workbench 'Object' color mode reads obj.color -- enable it so the
    per-object tints above actually show up in the render."""
    scene = bpy.context.scene
    shading = bpy.context.scene.display.shading
    shading.color_type = "OBJECT"
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.show_object_outline = True


def setup_camera_and_animation():
    bpy.ops.object.camera_add(location=(0, -12, 4), rotation=(math.radians(78), 0, 0))
    cam = bpy.context.active_object
    cam.name = "MainCamera"
    cam.data.lens = 35  # moderate establishing lens -- avoids ultra-wide corner distortion
    bpy.context.scene.camera = cam

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = END_FRAME
    scene.render.fps = FPS

    # Ease in/out on newly-inserted keyframes for a smooth cinematic move.
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "SINE"

    # Keyframe 1: wide establishing position, centered on the terrace/pool axis.
    cam.location = (0, -12, 4)
    cam.rotation_euler = (math.radians(78), 0, 0)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.keyframe_insert(data_path="rotation_euler", frame=1)

    # Keyframe END: pushed in toward the pool/ocean, same centered axis.
    cam.location = (0, -5, 3)
    cam.rotation_euler = (math.radians(81), 0, 0)
    cam.keyframe_insert(data_path="location", frame=END_FRAME)
    cam.keyframe_insert(data_path="rotation_euler", frame=END_FRAME)


def add_lighting():
    bpy.ops.object.light_add(type="SUN", location=(-10, -10, 15))
    sun = bpy.context.active_object
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(-35))

    # Warm sky-blue world background instead of the workbench default black --
    # this is a conditioning anchor for a "golden hour" Veo prompt, and a black
    # void behind the blockout would bias the generation toward a night scene.
    # BLENDER_WORKBENCH ignores world shader nodes, so use the flat World.color.
    world = bpy.data.worlds.new("VillaSky")
    world.use_nodes = False
    world.color = (0.65, 0.82, 0.92)
    bpy.context.scene.world = world


def configure_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    set_object_color_display()


def render_reference_frame():
    scene = bpy.context.scene
    scene.frame_set(1)
    scene.render.filepath = str(OUT / "reference_frame.png")
    bpy.ops.render.render(write_still=True)
    print(f"saved {scene.render.filepath}")


def render_playblast():
    """Optional: render all 120 frames as PNGs then mux to mp4 with ffmpeg
    (Blender's own FFMPEG output target needs codecs not guaranteed present
    in this pip-only bpy install, so this is more portable)."""
    frames_dir = OUT / "blockout_frames"
    frames_dir.mkdir(exist_ok=True)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    for f in range(1, END_FRAME + 1):
        scene.frame_set(f)
        scene.render.filepath = str(frames_dir / f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        str(OUT / "blockout.mp4"),
    ], check=True)
    print(f"saved {OUT / 'blockout.mp4'}")


def main():
    clear_scene()
    build_villa_terrace()
    add_lighting()
    setup_camera_and_animation()
    configure_render()
    render_reference_frame()
    if RENDER_VIDEO:
        render_playblast()


if __name__ == "__main__":
    main()

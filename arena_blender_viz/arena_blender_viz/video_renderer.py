"""
video_renderer.py: Still + animation rendering and MP4 muxing for
arena-blender-viz.

Both render paths drive Cycles from inside a background Blender process and
support rendering one camera, several named cameras, or every camera present in
the .blend -- all in a single Blender launch, since opening the .blend is the
expensive part and the camera list is only knowable once it is open.

Blender's internal video output is unreliable across builds, so animations
are rendered as PNG frame sequences and muxed externally (imageio-ffmpeg
preferred, cv2 `mp4v` fallback). Frame sequences are resumable:
`--only-missing-frames` re-renders only absent PNGs.
"""
from __future__ import annotations

import os
import platform as _platform
import subprocess
import sys
from pathlib import Path

# Frame file pattern written by the bpy loop; keep in sync with _FRAME_SCRIPT.
FRAME_PATTERN = "frame_{frame:04d}.png"

# Marker the bpy scripts print for each finished image, parsed back by
# `_run_blender`. Only the file NAME is reported, never the full path, so the
# Windows/UNC path forms `_windows_form` produces never need translating back.
RENDERED_MARKER = "[RENDERED] "

# Cycles device selection, shared by both script templates. Blender silently
# falls back to CPU when the GPU backend cannot initialise -- containers
# routinely log "OptiX initialization failed with error code 7804" and
# "HIPEW initialization failed" -- so the device actually chosen is printed.
_GPU_CONFIG = """try:
    cprefs = bpy.context.preferences.addons['cycles'].preferences
    has_gpu = False
    for dev_type in ['OPTIX', 'CUDA', 'HIP']:
        try:
            cprefs.compute_device_type = dev_type
            cprefs.get_devices()
            devs = [d for d in cprefs.devices if d.type == dev_type]
            if devs:
                for d in devs:
                    d.use = True
                print('[GPU] Enabled', dev_type)
                has_gpu = True
                break
        except Exception:
            pass
    if not has_gpu:
        print('[CPU] Falling back to CPU render')
        scene.cycles.device = 'CPU'
except Exception as e:
    print('[!] Compute device configuration note:', e)
    scene.cycles.device = 'CPU'

# Ensure denoising does not crash if Blender build lacks OpenImageDenoiser
try:
    csettings = scene.cycles
    denoiser_val = getattr(csettings, 'denoiser', None)
    if not denoiser_val or denoiser_val not in ('OPENIMAGEDENOISE', 'OPTIX'):
        csettings.use_denoising = False
except Exception:
    pass"""

# Resolves the `__CAMERAS__` token into the `cams` list, shared by both
# templates. The token is either the string '__ALL__' or a list of names.
_CAMERA_RESOLVE = """cams, missing = [], []
names = __CAMERAS__
if names == '__ALL__':
    cams = sorted((o for o in bpy.data.objects if o.type == 'CAMERA'), key=lambda o: o.name)
    print('[Render] all %d camera(s) in scene: %s' % (
        len(cams), ', '.join(c.name for c in cams)), flush=True)
else:
    for n in names:
        o = bpy.data.objects.get(n)
        if o is not None and o.type == 'CAMERA':
            cams.append(o)
        else:
            missing.append(n)

if missing:
    print('[!] Not camera objects in this file: %s' % ', '.join(missing), flush=True)
if not cams:
    raise RuntimeError('no renderable camera found (requested: %r)' % (names,))"""

# Still-image template; `__TOKEN__` placeholders are replaced before invocation.
# Kept as a plain (non-f) string so braces need no escaping.
_STILL_SCRIPT = """import bpy
import os

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'

__GPU_CONFIG__

__RES_OVERRIDES__
__SAMPLE_OVERRIDES__
__PCT_OVERRIDES__
__DPI_OVERRIDES__

print('[Render Config] Resolution: %dx%d (%d%%), Samples: %d' % (
    scene.render.resolution_x, scene.render.resolution_y,
    scene.render.resolution_percentage, scene.cycles.samples), flush=True)

__CAMERA_RESOLVE__

__FRAME_SET__

out_dir = __OUTDIR__
pattern = __FILEPAT__
os.makedirs(out_dir, exist_ok=True)

for cam in cams:
    scene.camera = cam
    fname = pattern % cam.name if '%s' in pattern else pattern
    scene.render.filepath = os.path.join(out_dir, fname)
    print('[Render] %s -> %s' % (cam.name, scene.render.filepath), flush=True)
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:
        print('[!] Render of %s failed with %s. Retrying with denoising disabled...' % (
            cam.name, e), flush=True)
        scene.cycles.use_denoising = False
        bpy.ops.render.render(write_still=True)
    print('__MARKER__%s\\t%s' % (cam.name, fname), flush=True)

print('[OK] Render completed: %d camera(s)' % len(cams), flush=True)
"""

# Animation frame-sequence template.
_FRAME_SCRIPT = """import bpy
import os

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.seed = __SEED__

__GPU_CONFIG__

__RES_OVERRIDES__
__SAMPLE_OVERRIDES__
__PCT_OVERRIDES__

print('[Render Config] Resolution: %dx%d (%d%%), Samples: %d' % (
    scene.render.resolution_x, scene.render.resolution_y,
    scene.render.resolution_percentage, scene.cycles.samples), flush=True)

__CAMERA_RESOLVE__

frame_end = scene.frame_end
if __END__ != None:
    frame_end = min(__END__, frame_end)
start = __START__ if __START__ != None else 1
stride = __STRIDE__
frames = list(range(start, frame_end + 1, stride))
if not frames:
    print('[!] Empty frame range (start=%s end=%s stride=%s)' % (start, frame_end, stride))
else:
    print('[Animate] %d frames (%d..%d, stride %d)' % (
        len(frames), frames[0], frames[-1], stride), flush=True)

out_dir = __OUTDIR__
per_camera_dir = __PER_CAMERA_DIR__
only_missing = __ONLY_MISSING__

for cam in cams:
    scene.camera = cam
    # Several cameras need their own frame sequence, otherwise the PNGs of one
    # camera overwrite the next.
    cam_dir = os.path.join(out_dir, cam.name) if per_camera_dir else out_dir
    os.makedirs(cam_dir, exist_ok=True)
    done = 0
    for i, f in enumerate(frames):
        fpath = os.path.join(cam_dir, 'frame_%04d.png' % f)
        if only_missing and os.path.isfile(fpath):
            continue
        scene.frame_set(f)
        scene.render.filepath = fpath
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as e:
            print('[!] Frame %d failed with %s. Retrying with denoising disabled...' % (f, e))
            scene.cycles.use_denoising = False
            bpy.ops.render.render(write_still=True)
        done += 1
        if done % 10 == 0 or i == len(frames) - 1:
            print('[Animate] %s: rendered %d/%d frames' % (cam.name, done, len(frames)), flush=True)
    print('__MARKER__%s\\t%s' % (cam.name, cam_dir), flush=True)

print('[OK] Frame sequence completed (%d camera(s))' % len(cams), flush=True)
"""


def _token_replace(template: str, **tokens: object) -> str:
    expr = template
    for key, value in tokens.items():
        expr = expr.replace(f"__{key}__", str(value))
    return expr


def _windows_form(p: Path, blender_exe: Path | None = None) -> str:
    """Return `p` in a form the target Blender executable can open.

    Under WSL with a Windows Blender (.exe), absolute POSIX paths handed
    through interop get resolved against the Windows process cwd and come
    out doubled, so they are converted to \\\\wsl.localhost\\<distro>\\... UNC
    form via `wslpath -w`. Native Windows and native Linux Blender binaries
    receive the path unchanged. When `blender_exe` is None the conversion is
    skipped.
    """
    s = str(p)
    is_windows_blender = blender_exe is not None and blender_exe.name.lower().endswith(".exe")
    if (
        is_windows_blender
        and _platform.system() != "Windows"
        and s.startswith("/")
        and not s.startswith(("//wsl", "//WSL"))
    ):
        try:
            converted = subprocess.run(
                ["wslpath", "-w", s], capture_output=True, text=True, check=True
            ).stdout.strip()
            if converted:
                return converted
        except Exception:
            pass
    return s


def camera_names(camera: str | list[str] | None) -> list[str] | None:
    """Normalise a camera selection to names, or None for "every camera".

    `None`, `"all"` and `"*"` all mean every camera in the .blend. A
    comma-separated string or a list selects those cameras by name.
    """
    if camera is None:
        return None
    if isinstance(camera, str):
        from .cli import parse_camera_spec  # lazy: cli imports this module

        return parse_camera_spec(camera)
    return [str(n) for n in camera] or None


def camera_token(camera: str | list[str] | None) -> str:
    """Render the `__CAMERAS__` token: `'__ALL__'` or a Python list literal."""
    names = camera_names(camera)
    # repr() keeps names containing quotes/backslashes valid Python literals.
    return "'__ALL__'" if names is None else repr(names)


def _run_blender(
    expr: str, blend_path: Path, blender_exe: Path, what: str
) -> list[tuple[str, str]]:
    """Run `expr` in background Blender, returning its `[RENDERED]` reports.

    Blender's output is streamed line by line rather than captured, so Cycles
    progress stays visible while the machine-readable lines are parsed back
    out. `--python-exit-code 1` makes a Python-level failure (a camera that
    does not exist, a render that cannot start) surface as a non-zero exit
    instead of being reported as success.
    """
    cmd = [
        str(blender_exe),
        "--background",
        _windows_form(blend_path, blender_exe),
        "--python-exit-code", "1",
        "--python-expr", expr,
    ]
    print(f"[*] Rendering {what} with {blender_exe.name}...", flush=True)
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    rendered: list[tuple[str, str]] = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        print(line, flush=True)
        if line.startswith(RENDERED_MARKER):
            cam_name, _, fname = line[len(RENDERED_MARKER):].partition("\t")
            if fname:
                rendered.append((cam_name, fname))
    proc.wait()
    if proc.returncode != 0:
        print(f"[!] Blender exited with code {proc.returncode}")
        sys.exit(proc.returncode)
    return rendered


def render_stills(
    blend_path: Path,
    camera: str | list[str] | None,
    out_dir: Path,
    filename_pattern: str = "%s.png",
    frame: int | None = None,
    resolution: list[int] | None = None,
    percentage: int | None = None,
    samples: int | None = None,
    dpi: int | None = None,
    blender_exe: Path | None = None,
) -> list[tuple[str, Path]]:
    """Render one still per selected camera.

    `filename_pattern` is joined onto `out_dir`; when it contains `%s` that is
    replaced with the camera name (required whenever more than one camera may
    be rendered, since the names of an "all cameras" selection are only known
    once the .blend is open). Returns `(camera_name, image_path)` pairs.
    """
    if blender_exe is None:
        blender_exe = _find_blender()

    res_overrides = ""
    if resolution:
        res_overrides = (
            f"scene.render.resolution_x = {int(resolution[0])}\n"
            f"scene.render.resolution_y = {int(resolution[1])}"
        )
    sample_overrides = f"scene.cycles.samples = {int(samples)}" if samples else ""
    pct_overrides = f"scene.render.resolution_percentage = {int(percentage)}" if percentage else ""
    dpi_overrides = ""
    if dpi:
        dpi_overrides = (
            "# DPI scaling relative to the standard 300 DPI publication baseline\n"
            f"dpi_scale = {dpi} / 300.0\n"
            "scene.render.resolution_x = int(scene.render.resolution_x * dpi_scale)\n"
            "scene.render.resolution_y = int(scene.render.resolution_y * dpi_scale)"
        )

    expr = _token_replace(
        _STILL_SCRIPT,
        GPU_CONFIG=_GPU_CONFIG,
        CAMERA_RESOLVE=_CAMERA_RESOLVE,
        MARKER=RENDERED_MARKER,
        RES_OVERRIDES=res_overrides,
        SAMPLE_OVERRIDES=sample_overrides,
        PCT_OVERRIDES=pct_overrides,
        DPI_OVERRIDES=dpi_overrides,
        CAMERAS=camera_token(camera),
        # repr(), not a raw string: Windows paths are full of backslashes and a
        # trailing one would escape the closing quote.
        OUTDIR=repr(_windows_form(out_dir, blender_exe)),
        FILEPAT=repr(filename_pattern),
        FRAME_SET=(
            f"scene.frame_set({int(frame)})"
            if frame is not None
            else "# Keep scene active frame (worst-case frame)"
        ),
    )

    names = camera_names(camera)
    what = f"camera '{names[0]}'" if names and len(names) == 1 else f"{len(names) if names else 'all'} camera(s)"

    out_dir.mkdir(parents=True, exist_ok=True)
    report = _run_blender(expr, blend_path, blender_exe, what)
    return [(cam, out_dir / fname) for cam, fname in report]


def render_frames(
    blend_path: Path,
    camera: str | list[str] | None,
    frames_dir: Path,
    start: int | None = None,
    end: int | None = None,
    stride: int = 1,
    resolution: list[int] | None = None,
    percentage: int | None = None,
    samples: int | None = None,
    only_missing: bool = False,
    seed: int = 0,
    blender_exe: Path | None = None,
) -> list[tuple[str, Path]]:
    """Render the animation frame sequence of `blend_path` into `frames_dir`.

    Frame N maps to scene time (N-1)/fps, matching the acoustic MOVIE-texture
    timeline (frame_start=1, frame_offset=0) so scene frames and field frames
    stay synchronized.

    A single camera writes `frame_*.png` straight into `frames_dir`, as before.
    Multiple cameras (or "all cameras") each get `frames_dir/<camera>/`, since
    the sequences would otherwise overwrite one another. Returns
    `(camera_name, frames_dir)` pairs.
    """
    if stride < 1:
        raise ValueError("stride must be >= 1")

    if blender_exe is None:
        blender_exe = _find_blender()

    names = camera_names(camera)
    # One camera keeps the historical layout (frames directly in `frames_dir`);
    # anything broader needs a directory per camera or the sequences collide.
    per_camera_dir = names is None or len(names) > 1

    res_overrides = ""
    if resolution:
        res_overrides = (
            f"scene.render.resolution_x = {int(resolution[0])}\n"
            f"scene.render.resolution_y = {int(resolution[1])}"
        )
    sample_overrides = f"scene.cycles.samples = {int(samples)}" if samples else ""
    pct_overrides = f"scene.render.resolution_percentage = {int(percentage)}" if percentage else ""

    expr = _token_replace(
        _FRAME_SCRIPT,
        GPU_CONFIG=_GPU_CONFIG,
        CAMERA_RESOLVE=_CAMERA_RESOLVE,
        MARKER=RENDERED_MARKER,
        SEED=int(seed),
        RES_OVERRIDES=res_overrides,
        SAMPLE_OVERRIDES=sample_overrides,
        PCT_OVERRIDES=pct_overrides,
        CAMERAS=camera_token(camera),
        START=start if start is not None else "None",
        END=end if end is not None else "None",
        STRIDE=int(stride),
        PER_CAMERA_DIR=per_camera_dir,
        OUTDIR=repr(_windows_form(frames_dir, blender_exe)),
        ONLY_MISSING="True" if only_missing else "False",
    )

    frames_dir.mkdir(parents=True, exist_ok=True)
    report = _run_blender(expr, blend_path, blender_exe, "animation frames")
    # The script reports the directory it wrote into, which `_windows_form` may
    # have rewritten; re-derive the local path rather than trusting the echo.
    return [
        (cam, (frames_dir / cam if per_camera_dir else frames_dir))
        for cam, _ in report
    ]


def _find_blender() -> Path:
    from .cli import find_blender

    return find_blender()


def mux_frames_mp4(
    frames_dir: Path,
    out_mp4: Path,
    fps: float = 30.0,
    crf: int = 18,
) -> Path:
    """Mux `frame_*.png` files into an H.264 MP4.

    Prefers imageio-ffmpeg (bundled static ffmpeg, no system dependency);
    falls back to cv2 `mp4v` when imageio/ffmpeg is unavailable.
    """
    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"No frame_*.png files found in {frames_dir}")

    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    try:
        import imageio.v2 as imageio

        writer = imageio.get_writer(
            str(out_mp4),
            fps=fps,
            codec="libx264",
            output_params=["-crf", str(crf), "-pix_fmt", "yuv420p"],
        )
        for f in frames:
            writer.append_data(imageio.imread(str(f)))
        writer.close()
        print(f"[OK] Muxed {len(frames)} frames with imageio-ffmpeg (crf={crf})")
        return out_mp4
    except Exception as e:
        print(f"[!] imageio-ffmpeg mux failed ({e}); falling back to cv2 mp4v")

    import cv2

    first = cv2.imread(str(frames[0]))
    if first is None:
        raise RuntimeError(f"Could not read first frame {frames[0]}")
    h, w = first.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_mp4), fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"cv2 VideoWriter could not open {out_mp4}")
    for f in frames:
        img = cv2.imread(str(f))
        if img is None:
            print(f"[!] Skipping unreadable frame {f}")
            continue
        writer.write(img)
    writer.release()
    print(f"[OK] Muxed {len(frames)} frames with cv2 mp4v")
    return out_mp4

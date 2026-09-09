"""
video_renderer.py: Animation frame-sequence rendering + MP4 muxing for
arena-blender-viz.

Blender's internal video output is unreliable across builds, so animations
are rendered as PNG frame sequences with Cycles and muxed externally
(imageio-ffmpeg preferred, cv2 `mp4v` fallback). Frame sequences are
resumable: `--only-missing-frames` re-renders only absent PNGs.
"""
from __future__ import annotations

import platform as _platform
import subprocess
import sys
from pathlib import Path

# Frame file pattern written by the bpy loop; keep in sync with _FRAME_SCRIPT.
FRAME_PATTERN = "frame_{frame:04d}.png"

# Blender python-expr template; `__TOKEN__` placeholders are replaced before
# invocation. Kept as a plain (non-f) string so braces need no escaping.
_FRAME_SCRIPT = """import bpy
import os

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.seed = __SEED__

try:
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

# Ensure denoising does not crash if the Blender build lacks OpenImageDenoiser
try:
    csettings = scene.cycles
    denoiser_val = getattr(csettings, 'denoiser', None)
    if not denoiser_val or denoiser_val not in ('OPENIMAGEDENOISE', 'OPTIX'):
        csettings.use_denoising = False
except Exception:
    pass

__RES_OVERRIDES__
__SAMPLE_OVERRIDES__
__PCT_OVERRIDES__

print('[Render Config] Resolution: %dx%d (%d%%), Samples: %d' % (
    scene.render.resolution_x, scene.render.resolution_y,
    scene.render.resolution_percentage, scene.cycles.samples))

cam = bpy.data.objects.get('__CAMERA__')
if cam:
    scene.camera = cam

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
        len(frames), frames[0], frames[-1], stride))

out_dir = r'__OUTDIR__'
os.makedirs(out_dir, exist_ok=True)
only_missing = __ONLY_MISSING__

done = 0
for i, f in enumerate(frames):
    fpath = os.path.join(out_dir, 'frame_%04d.png' % f)
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
        print('[Animate] rendered %d/%d frames' % (done, len(frames)), flush=True)

print('[OK] Frame sequence completed')
"""


def _token_replace(template: str, **tokens: object) -> str:
    expr = template
    for key, value in tokens.items():
        expr = expr.replace(f"__{key}__", str(value))
    return expr


def _windows_form(p: Path) -> str:
    """Return `p` in a form the (Windows) Blender executable can open.

    Under WSL with a Windows Blender, absolute POSIX paths handed through
    interop get resolved against the Windows process cwd and come out
    doubled, so they are converted to \\\\wsl.localhost\\<distro>\\... UNC
    form via `wslpath -w`. On Windows the path passes through unchanged.
    """
    s = str(p)
    if _platform.system() != "Windows" and s.startswith("/") and not s.startswith(("//wsl", "//WSL")):
        try:
            converted = subprocess.run(
                ["wslpath", "-w", s], capture_output=True, text=True, check=True
            ).stdout.strip()
            if converted:
                return converted
        except Exception:
            pass
    return s


def render_frames(
    blend_path: Path,
    camera: str,
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
) -> Path:
    """Render the animation frame sequence of `blend_path` into `frames_dir`.

    Frame N maps to scene time (N-1)/fps, matching the acoustic MOVIE-texture
    timeline (frame_start=1, frame_offset=0) so scene frames and field frames
    stay synchronized.
    """
    if stride < 1:
        raise ValueError("stride must be >= 1")

    if blender_exe is None:
        from .cli import find_blender

        blender_exe = find_blender()

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
        SEED=int(seed),
        RES_OVERRIDES=res_overrides,
        SAMPLE_OVERRIDES=sample_overrides,
        PCT_OVERRIDES=pct_overrides,
        CAMERA=camera,
        START=start if start is not None else "None",
        END=end if end is not None else "None",
        STRIDE=int(stride),
        OUTDIR=_windows_form(frames_dir),
        ONLY_MISSING="True" if only_missing else "False",
    )

    frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(blender_exe),
        "--background",
        _windows_form(blend_path),
        "--python-expr",
        expr,
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print(f"[!] Blender frame rendering exited with code {res.returncode}")
        sys.exit(res.returncode)
    return frames_dir


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

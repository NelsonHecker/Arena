"""
cli.py: Main CLI entry point for arena-blender-viz.
Provides commands:
  arena-blender-viz build   - Generates .blend scene from world.yaml + benchmark episode
  arena-blender-viz render  - Renders image from a specific camera in a .blend scene
  arena-blender-viz animate - Renders an animation frame sequence and muxes it to MP4
  arena-blender-viz hud     - Generates publication HUD cards, color scales, or composites onto renders
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .bundle_builder import BundleBuilder

import platform as _platform
if _platform.system() == "Windows":
    BLENDER_EXE = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
else:
    BLENDER_EXE = Path("/usr/bin/blender")
SCRIPT_DIR = Path(__file__).parent


def _bool_flag(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return True
    return str(v).strip().lower() not in ("false", "0", "no", "f", "off")


def _blender_version(exe: Path) -> tuple[int, int, int] | None:
    """Query `exe --version` and return (major, minor, patch), or None."""
    try:
        out = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        m = re.search(r"Blender\s+(\d+)\.(\d+)(?:\.(\d+))?", out.stdout or out.stderr)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    except Exception:
        pass
    return None


def find_blender() -> Path:
    import shutil

    # 0. Explicit override via environment variable (highest priority)
    env_exe = os.environ.get("BLENDER_EXE")
    if env_exe:
        p = Path(env_exe)
        if p.is_file():
            return p

    # Collect candidates in priority order.
    candidates: list[Path] = []

    # 1. Platform-specific well-known path
    if BLENDER_EXE.is_file():
        candidates.append(BLENDER_EXE)

    # 2. Anywhere on PATH (covers /usr/bin/blender, snap, conda, etc.)
    p = shutil.which("blender")
    if p:
        candidates.append(Path(p))

    # 3. WSL2: Windows Blender mounted under /mnt/c  (the exe runs via WSL interop)
    #    Glob all installed versions, newest first.
    _wsl_base = Path("/mnt/c/Program Files/Blender Foundation")
    if _wsl_base.is_dir():
        candidates.extend(
            sorted(
                _wsl_base.glob("Blender */blender.exe"),
                key=lambda p: p.parent.name,
                reverse=True,  # newest version first
            )
        )

    # 4. Common Linux / Docker install locations
    _linux_candidates = [
        Path("/usr/bin/blender"),
        Path("/usr/local/bin/blender"),
        Path("/snap/bin/blender"),
        Path("/opt/blender/blender"),
    ]
    for cand in _linux_candidates:
        if cand.is_file():
            candidates.append(cand)

    # Dedupe, preserving the priority order above.
    _seen: set[str] = set()
    _unique: list[Path] = []
    for cand in candidates:
        key = str(cand).lower()
        if key not in _seen:
            _seen.add(key)
            _unique.append(cand)

    # Prefer the highest Blender version across all candidates
    # (e.g. /opt/blender/blender 5.2.x wins over /usr/bin/blender 4.0.x).
    best: Path | None = None
    best_ver: tuple[int, int, int] | None = None
    for cand in _unique:
        ver = _blender_version(cand)
        if ver and (best_ver is None or ver > best_ver):
            best, best_ver = cand, ver
    if best:
        return best
    # Fall back to the first candidate if every --version query failed
    if _unique:
        return _unique[0]

    _searched = (
        ["$BLENDER_EXE (not set)", str(BLENDER_EXE), "PATH",
         str(_wsl_base / "Blender *" / "blender.exe")]
        + [str(c) for c in _linux_candidates]
    )
    raise FileNotFoundError(
        "Blender executable not found.  Searched:\n"
        + "\n".join(f"  {s}" for s in _searched)
        + "\n\nOptions:\n"
        "  • WSL:    Blender installs to C:\\Program Files\\Blender Foundation and is "
        "auto-detected via /mnt/c/Program Files/Blender Foundation/Blender X.Y/blender.exe\n"
        "  • Linux:  extract an official blender-*-linux-x64 tarball to /opt/blender "
        "(or place blender on PATH)\n"
        "  • Any:    set env var BLENDER_EXE=/full/path/to/blender"
    )


_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".webp", ".bmp")

# `--camera` values that mean "every camera in the .blend".
_ALL_CAMERA_WORDS = ("all", "*")


def parse_camera_spec(spec: str | None) -> list[str] | None:
    """Parse a `--camera` value into names, or None for "every camera".

    `all` / `*` selects every camera in the .blend -- including any added by
    hand in the Blender GUI, not just the built-in presets. A comma-separated
    list (or a single name) selects those cameras; several are rendered in one
    Blender launch rather than one launch each.
    """
    s = (spec or "").strip()
    if not s or s.lower() in _ALL_CAMERA_WORDS:
        return None
    return [n.strip() for n in s.split(",") if n.strip()] or None


def _is_absolute_like(p: str) -> bool:
    """True for POSIX paths, Windows drive paths (`C:/...`) and UNC paths.

    The CLI also runs under WSL, where `Path("C:/x").is_absolute()` is False
    even though the caller clearly meant an absolute Windows path.
    """
    return p.startswith(("/", "\\")) or (len(p) >= 2 and p[1] == ":")


def resolve_render_targets(
    blend_path: Path, output_arg: str | None, cameras: list[str] | None
) -> tuple[Path, str]:
    """Resolve `(output_dir, filename_pattern)` for a still render.

    `cameras` is None for "every camera in the scene", else the requested names.
    For a single named camera the pattern holds no `%s`, so `--output` keeps
    meaning "exactly this file" as it always has. For several (or all) cameras
    the pattern holds a `%s` that the Blender-side script substitutes with the
    camera name -- the names in an "all" selection are only known once the
    .blend is open.
    """
    single = cameras is not None and len(cameras) == 1

    def _abs(p: str) -> Path:
        return Path(p) if _is_absolute_like(p) else blend_path.parent / p

    if output_arg:
        if single:
            base = _abs(str(output_arg))
            return base.parent, base.name
        if Path(str(output_arg)).suffix.lower() in _IMAGE_SUFFIXES:
            base = _abs(str(output_arg))
            return base.parent, f"{base.stem}_%s{base.suffix}"
        # No image suffix: the argument names a destination directory.
        return _abs(str(output_arg)), f"{blend_path.stem}_%s.png"

    if single:
        return blend_path.parent, f"{blend_path.stem}_{cameras[0]}.png"
    return blend_path.parent, f"{blend_path.stem}_%s.png"


def _map_telemetry_frame(target_frame: int | None, blend_path: Path) -> int | None:
    """Map an episode telemetry row index onto a Blender animation frame.

    The sibling `<blend>_bundle.json` records the robot trajectory the scene was
    built from, so a telemetry frame index can be converted to the animation
    frame that corresponds to the same instant.
    """
    if target_frame is None:
        return None
    bundle_cand = blend_path.parent / f"{blend_path.stem}_bundle.json"
    if not bundle_cand.is_file():
        return target_frame
    try:
        import json

        bdata = json.loads(bundle_cand.read_text())
        traj = bdata.get("telemetry", {}).get("robot_trajectory", [])
        fps = bdata.get("options", {}).get("fps", 30)
        if traj and target_frame < len(traj):
            mapped = max(1, int(traj[target_frame]["t"] * fps))
            print(
                f"[*] Mapping telemetry frame {target_frame} "
                f"(t={traj[target_frame]['t']}s) to animation frame {mapped}"
            )
            return mapped
    except Exception:
        pass
    return target_frame


def resolve_data_dir() -> Path:
    if "ARENA_DATA_DIR" in os.environ:
        p = Path(os.environ["ARENA_DATA_DIR"])
        if p.is_dir():
            return p
    if "ARENA_WS_DIR" in os.environ:
        p = Path(os.environ["ARENA_WS_DIR"]) / "data"
        if p.is_dir():
            return p
    for cand in [
        Path("/opt/arena_ws/data"),
        Path("u:/data"),
        Path("/data"),
    ]:
        if cand.is_dir():
            return cand
    return Path("/opt/arena_ws/data")


def resolve_world_path(world_arg: str) -> Path:
    p = Path(world_arg)
    if p.is_file():
        return p
    search_roots: list[Path] = []
    if "ARENA_DIR" in os.environ:
        search_roots.append(Path(os.environ["ARENA_DIR"]) / "arena_simulation_setup" / "worlds")
    if "ARENA_WS_DIR" in os.environ:
        search_roots.append(Path(os.environ["ARENA_WS_DIR"]) / "src" / "Arena" / "arena_simulation_setup" / "worlds")
    search_roots.extend([
        Path("/opt/arena_ws/src/Arena/arena_simulation_setup/worlds"),
        Path("u:/src/Arena/arena_simulation_setup/worlds"),
        Path(__file__).resolve().parent.parent.parent / "arena_simulation_setup" / "worlds",
    ])
    for base_worlds in search_roots:
        candidates = [
            base_worlds / world_arg / "0" / "world.yaml",
            base_worlds / world_arg / "world.yaml",
            base_worlds / world_arg,
        ]
        for c in candidates:
            if c.is_file():
                return c
    raise FileNotFoundError(f"Could not find world.yaml for '{world_arg}' across {search_roots}")


def benchmark_search_roots() -> list[Path]:
    """Directories that may contain `<benchmark run>` directories."""
    roots: list[Path] = []
    if "ARENA_DATA_DIR" in os.environ:
        roots.append(Path(os.environ["ARENA_DATA_DIR"]) / "benchmarks")
    if "ARENA_WS_DIR" in os.environ:
        roots.append(Path(os.environ["ARENA_WS_DIR"]) / "data" / "benchmarks")
    roots.extend([
        Path("/opt/arena_ws/data/benchmarks"),
        Path("u:/data/benchmarks"),
        Path("/data/benchmarks"),
    ])
    return roots


def resolve_benchmark_dir(benchmark_arg: str) -> Path | None:
    """Resolve a benchmark name or path to its directory, or None."""
    bench_p = Path(benchmark_arg)
    if bench_p.is_dir():
        return bench_p
    for root in benchmark_search_roots():
        cand = root / benchmark_arg
        if cand.is_dir():
            return cand
    return None


def resolve_blend_path(
    blend_arg: str,
    benchmark_arg: str | None = None,
    episode_arg: str | None = None,
) -> Path:
    """Resolve a `--blend` value to an existing .blend file.

    Accepts an explicit path, or a bare stem like `office_1_ep005_static`. A
    stem is looked up in the benchmark's `blender/` output directory -- where
    `build` writes scenes -- and then across the data directories, so with a
    `--benchmark`/`--episode` pair the name alone is enough.

    `--blend office_1 --episode 005` also works: when the given name has no
    `_ep<NNN>` tag of its own, the episode tag is appended and retried.
    """
    raw = str(blend_arg).strip()
    p = Path(raw).expanduser()

    if p.is_dir():
        found = sorted(p.glob("*.blend"))
        if len(found) == 1:
            print(f"[*] Resolved --blend '{raw}' -> {found[0]}")
            return found[0].resolve()
        listing = "\n".join(f"    {f.name}" for f in found) or "    (none)"
        raise FileNotFoundError(
            f"'{raw}' is a directory holding {len(found)} .blend files; name one:\n{listing}"
        )
    if p.is_file():
        return p.resolve()

    names = [raw] if raw.lower().endswith(".blend") else [raw, f"{raw}.blend"]

    if episode_arg is not None:
        ep_tag = _episode_tag(episode_arg)
        stems = [n[: -len(".blend")] if n.lower().endswith(".blend") else n for n in names]
        for stem in stems:
            if ep_tag not in stem:
                names += [f"{stem}{ep_tag}{sfx}.blend" for sfx in ("", "_static")]

    dirs = _blend_search_dirs(benchmark_arg, episode_arg)
    for d in dirs:
        for n in dict.fromkeys(names):  # dedupe, keep order
            cand = d / n
            if cand.is_file():
                print(f"[*] Resolved --blend '{raw}' -> {cand}")
                return cand.resolve()

    # Name the siblings of whichever directory is most likely to hold the
    # intended scene, rather than the union across every searched directory.
    nearby_dir, nearby = None, []
    for d in dirs:
        found = sorted(f.name for f in d.glob("*.blend"))
        if found:
            nearby_dir, nearby = d, found
            break

    raise FileNotFoundError(
        f"Could not find a .blend for '{raw}'.\n"
        f"  Looked for: {', '.join(dict.fromkeys(names))}\n"
        f"  In: {', '.join(str(d) for d in dirs) or '(no candidate directories)'}\n"
        + (
            f"  Available in {nearby_dir}:\n"
            + "\n".join(f"    {n}" for n in nearby[:25])
            + "\n" if nearby else ""
        )
        + "  Pass a full path, or a --benchmark/--episode pair to resolve by name."
    )


def _episode_tag(episode_arg: str) -> str:
    """`005`, `episode_005` and `ep_005` all normalise to `_ep005`."""
    try:
        clean = str(episode_arg).lower().replace("episode_", "").replace("ep_", "").strip()
        return f"_ep{int(clean):03d}"
    except ValueError:
        return f"_{episode_arg}"


def _blend_search_dirs(
    benchmark_arg: str | None, episode_arg: str | None
) -> list[Path]:
    """Directories to search for a named .blend, most specific first."""
    dirs: list[Path] = []

    def add(d: Path) -> None:
        if d.is_dir() and d not in dirs:
            dirs.append(d)

    if benchmark_arg:
        bench_p = resolve_benchmark_dir(benchmark_arg)
        if bench_p is not None:
            add(bench_p / "blender")  # where `build` writes scenes
            add(bench_p)
            if episode_arg:
                ep_dir = resolve_episode_dir(str(bench_p), episode_arg)
                if ep_dir is not None:
                    add(ep_dir / "blender")
                    add(ep_dir)

    data_dir = resolve_data_dir()
    blender_root = data_dir / "blender"
    add(blender_root)
    if blender_root.is_dir():
        # data/blender/<world>/<world>.blend
        for sub in sorted(blender_root.iterdir()):
            add(sub)

    bench_root = data_dir / "benchmarks"
    if bench_root.is_dir():
        # data/benchmarks/<run>/blender/<world>_ep<NNN>.blend
        for sub in sorted(bench_root.iterdir()):
            add(sub / "blender")

    return dirs


def resolve_episode_dir(benchmark_arg: str, episode_arg: str | None = None) -> Path | None:
    bench_p = resolve_benchmark_dir(benchmark_arg)

    if bench_p is None or not bench_p.is_dir():
        return None

    if episode_arg:
        try:
            ep_clean = str(episode_arg).lower().replace("episode_", "").replace("ep_", "").strip()
            ep_num = int(ep_clean)
            cand_ep = bench_p / "episodes" / f"episode_{ep_num:03d}"
            if cand_ep.is_dir():
                return cand_ep
        except ValueError:
            pass
        ep_dir = bench_p / "episodes" / str(episode_arg)
        if ep_dir.is_dir():
            return ep_dir

    # Default to first episode
    episodes_dir = bench_p / "episodes"
    if episodes_dir.is_dir():
        first = next(episodes_dir.glob("episode_*"), None)
        if first and first.is_dir():
            return first

    return None


def cmd_build(args: argparse.Namespace) -> None:
    world_yaml = resolve_world_path(args.world)
    episode_dir = resolve_episode_dir(args.benchmark, args.episode) if args.benchmark else None
    acoustic_png = Path(args.acoustic_overlay) if args.acoustic_overlay else None

    world_name = world_yaml.parent.parent.name if world_yaml.parent.name == "0" else world_yaml.parent.name

    # A static build is a different artifact from the animated one, so give it its
    # own default name rather than overwriting the animated .blend.
    static_mode = bool(getattr(args, "static", False))
    name_suffix = "_static" if static_mode else ""

    if args.output:
        out_blend = Path(args.output)
    else:
        data_dir = resolve_data_dir()
        if episode_dir:
            # Place in <benchmark_dir>/blender/<world_name>_ep<num>.blend
            bench_root = episode_dir.parent.parent
            blender_out_dir = bench_root / "blender"
            try:
                ep_clean = str(episode_dir.name).lower().replace("episode_", "").replace("ep_", "").strip()
                ep_tag = f"_ep{int(ep_clean):03d}"
            except ValueError:
                ep_tag = f"_{episode_dir.name}"
            out_blend = blender_out_dir / f"{world_name}{ep_tag}{name_suffix}.blend"
        else:
            # Place in data/blender/<world_name>/<world_name>.blend
            blender_out_dir = data_dir / "blender" / world_name
            out_blend = blender_out_dir / f"{world_name}{name_suffix}.blend"

    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bundle_json = out_blend.parent / f"{out_blend.stem}_bundle.json"

    options = {
        "animate_doors": not args.no_animate_doors,
        "animate_peds": not args.no_animate_peds,
        "show_door_radius": args.show_door_radius,
        "show_encounters": getattr(args, "show_encounters", False),
        "show_energy_glow": args.show_energy_glow,
        "glow_metric": args.glow_metric,
        "glow_strength": args.glow_strength,
        "additive_start_dba": args.additive_start_dba,
        "additive_full_dba": args.additive_full_dba,
        "auto_texture": not args.no_auto_texture,
        "fill_light_strength": args.fill_light_strength,
        "floor_brightness": args.floor_brightness,
        "glow_energy_vmin": getattr(args, "glow_energy_vmin", None),
        "glow_energy_vmax": getattr(args, "glow_energy_vmax", None),
        "glow_acoustic_vmin": getattr(args, "glow_acoustic_vmin", None),
        "glow_acoustic_vmax": getattr(args, "glow_acoustic_vmax", None),
        "trajectory_thickness": args.trajectory_thickness,
        "acoustic": args.acoustic or (args.acoustic_overlay is not None),
        "acoustic_mode": getattr(args, "acoustic_mode", "plain"),
        "frame": getattr(args, "frame", None),
        "time": getattr(args, "time", None),
        "scenario": getattr(args, "scenario", None),
        "static": static_mode,
    }

    print(f"[*] Building scene bundle from {world_yaml}...")
    builder = BundleBuilder(
        world_yaml_path=world_yaml,
        benchmark_episode_dir=episode_dir,
        acoustic_overlay_png=acoustic_png,
        options=options,
    )
    builder.build_bundle(bundle_json)
    print(f"[+] Bundle written to: {bundle_json}")

    # Invoke Blender to construct scene
    blender_path = find_blender()
    scene_builder_script = SCRIPT_DIR / "blender_scene_builder.py"
    from .video_renderer import _windows_form

    print(f"[*] Executing Blender scene assembly with {blender_path}...")
    cmd = [
        str(blender_path),
        "--background",
        "--python",
        _windows_form(scene_builder_script, blender_path),
        "--",
        _windows_form(bundle_json, blender_path),
        _windows_form(out_blend, blender_path),
    ]

    # Unbuffered child stdout, so build progress streams live. Without this the
    # output arrives in blocks and a slow stage looks like it hung on whichever
    # line happened to flush last, which makes stalls very hard to localise.
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    res = subprocess.run(cmd, env=env)
    if res.returncode == 0:
        print(f"[OK] Successfully created Blender scene: {out_blend}")
        print(f"    Open in Blender GUI: & '{blender_path}' '{out_blend}'")
    else:
        print(f"[!] Blender exited with code {res.returncode}")
        sys.exit(res.returncode)


def cmd_render(args: argparse.Namespace) -> None:
    from .video_renderer import render_stills

    try:
        blend_path = resolve_blend_path(
            args.blend,
            getattr(args, "benchmark", None),
            getattr(args, "episode", None),
        )
    except FileNotFoundError as e:
        print(f"[!] {e}")
        sys.exit(1)

    cameras = parse_camera_spec(args.camera)
    if cameras is None:
        print("[*] Camera selection: every camera in the scene")
    elif len(cameras) > 1:
        print(f"[*] Camera selection: {', '.join(cameras)}")

    out_dir, pattern = resolve_render_targets(blend_path, args.output, cameras)
    target_frame = _map_telemetry_frame(args.frame, blend_path)

    rendered = render_stills(
        blend_path=blend_path,
        camera=args.camera,
        out_dir=out_dir,
        filename_pattern=pattern,
        frame=target_frame,
        resolution=getattr(args, "resolution", None),
        percentage=getattr(args, "percentage", None),
        samples=getattr(args, "samples", None),
        dpi=getattr(args, "dpi", None),
        blender_exe=find_blender(),
    )

    if not rendered:
        print("[!] Blender reported no rendered images")
        sys.exit(1)
    for cam_name, out_p in rendered:
        print(f"[OK] Render saved ({cam_name}): {out_p}")

    # Optional HUD overlay generation, per rendered image
    if getattr(args, "hud", False):
        if not args.benchmark or not args.episode:
            print("[!] Note: --hud requires --benchmark and --episode to extract metrics. Skipping HUD.")
            return

        from .hud_generator import HUDGenerator

        metrics = HUDGenerator.extract_metrics(args.benchmark, args.episode)
        for _, out_p in rendered:
            card_path = out_p.with_name(f"{out_p.stem}_hud_card.png")
            cb_path = out_p.with_name(f"{out_p.stem}_colorbar.png")
            comp_path = out_p.with_name(f"{out_p.stem}_with_hud.png")

            HUDGenerator.generate_colorbar(cb_path, vmin=metrics.get("vmin", 20.0), vmax=metrics.get("vmax", 100.0))
            HUDGenerator.generate_hud_card(metrics, card_path)
            HUDGenerator.composite_onto_image(
                base_image_path=out_p,
                out_image_path=comp_path,
                hud_card_path=card_path,
                colorbar_path=cb_path,
                position=getattr(args, "hud_pos", "auto"),
                hud_scale_width_pct=getattr(args, "hud_scale", 0.25),
            )
            print(f"[OK] HUD Card: {card_path}")
            print(f"[OK] Colorbar: {cb_path}")
            print(f"[OK] Publication Composite with HUD: {comp_path}")


def cmd_animate(args: argparse.Namespace) -> None:
    from .video_renderer import render_frames, mux_frames_mp4

    try:
        blend_path = resolve_blend_path(
            args.blend,
            getattr(args, "benchmark", None),
            getattr(args, "episode", None),
        )
    except FileNotFoundError as e:
        print(f"[!] {e}")
        sys.exit(1)

    cameras = parse_camera_spec(args.camera)
    if cameras is None:
        print("[*] Camera selection: every camera in the scene")
    elif len(cameras) > 1:
        print(f"[*] Camera selection: {', '.join(cameras)}")

    out_mp4 = Path(args.output)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    frames_root = Path(args.frames_dir) if args.frames_dir else out_mp4.parent / f"{out_mp4.stem}_frames"

    rendered = render_frames(
        blend_path=blend_path,
        camera=args.camera,
        frames_dir=frames_root,
        start=args.start,
        end=args.end,
        stride=args.stride,
        resolution=args.resolution,
        percentage=args.percentage,
        samples=args.samples,
        only_missing=args.only_missing_frames,
        blender_exe=find_blender(),
    )
    if not rendered:
        print("[!] Blender reported no rendered frame sequences")
        sys.exit(1)

    # Several cameras get one MP4 each, suffixed with the camera name.
    multi = len(rendered) > 1
    for cam_name, frames_dir in rendered:
        target = out_mp4.with_name(f"{out_mp4.stem}_{cam_name}{out_mp4.suffix}") if multi else out_mp4
        print(f"[*] Muxing {cam_name} frames from {frames_dir} to {target} at {args.fps} fps...")
        mux_frames_mp4(frames_dir, target, fps=args.fps, crf=args.crf)
        print(f"[OK] Animation saved ({cam_name}): {target}")


def cmd_hud(args: argparse.Namespace) -> None:
    from .hud_generator import HUDGenerator
    bench_p = Path(args.benchmark)
    if not bench_p.is_dir():
        resolved = resolve_benchmark_dir(args.benchmark)
        if resolved is not None:
            bench_p = resolved

    metrics = HUDGenerator.extract_metrics(bench_p, args.episode)
    if args.output:
        out_dir = Path(args.output).parent
        stem = Path(args.output).stem
    else:
        out_dir = (bench_p / "hud") if bench_p.is_dir() else (resolve_data_dir() / "hud")
        try:
            ep_clean = str(args.episode).lower().replace("episode_", "").replace("ep_", "").strip()
            stem = f"episode_{int(ep_clean):03d}_hud"
        except ValueError:
            stem = f"episode_{args.episode}_hud"
    out_dir.mkdir(parents=True, exist_ok=True)

    cb_path = out_dir / f"{stem}_colorbar.png"
    card_path = out_dir / f"{stem}_card.png"

    HUDGenerator.generate_colorbar(cb_path, vmin=metrics.get("vmin", 20.0), vmax=metrics.get("vmax", 100.0))
    print(f"[+] Colorbar generated: {cb_path}")

    HUDGenerator.generate_hud_card(metrics, card_path)
    print(f"[+] HUD Card generated: {card_path}")

    if args.image:
        img_p = Path(args.image)
        comp_out = Path(args.output) if args.output else img_p.with_name(f"{img_p.stem}_with_hud.png")
        HUDGenerator.composite_onto_image(
            base_image_path=img_p,
            out_image_path=comp_out,
            hud_card_path=card_path,
            colorbar_path=cb_path,
            position=getattr(args, "pos", "auto"),
            hud_scale_width_pct=getattr(args, "scale", 0.25),
        )
        print(f"[+] Composited image saved: {comp_out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Arena 3.0 Blender Visualization Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: build
    p_build = subparsers.add_parser("build", help="Build a 3D Blender scene file from world and telemetry")
    p_build.add_argument("--world", required=True, help="World name (e.g. hospital_1) or path to world.yaml")
    p_build.add_argument("--benchmark", help="Benchmark run name or path to benchmark directory")
    p_build.add_argument("--episode", help="Episode ID (e.g. 008, 047)")
    p_build.add_argument("--acoustic-overlay", help="Path to acoustic field PNG heatmap")
    p_build.add_argument("--output", "-o", help="Output .blend file path")
    p_build.add_argument("--no-animate-doors", nargs="?", const=True, default=False, type=_bool_flag, help="Disable dynamic door sliding animation")
    p_build.add_argument("--no-animate-peds", nargs="?", const=True, default=False, type=_bool_flag, help="Disable dynamic pedestrian animation")
    p_build.add_argument("--static", nargs="?", const=True, default=False, type=_bool_flag,
                         help="Pose the world at a single instant and emit no animation data, so the .blend is directly editable and renderable as a still. Freezes at the worst-case acoustic frame unless --frame/--time is given.")
    p_build.add_argument("--show-door-radius", nargs="?", const=True, default=False, type=_bool_flag, help="Visualize door trigger activation radius (r=1.2m)")
    p_build.add_argument("--show-encounters", nargs="?", const=True, default=False, type=_bool_flag, help="Visualize personal space encounter disc overlays")
    p_build.add_argument("--show-energy-glow", nargs="?", const=True, default=False, type=_bool_flag,
                         help="Make the trajectory ribbon itself the glow: an emissive strip coloured by --glow-metric, brightened to read as a light source")
    p_build.add_argument("--glow-metric", choices=["acoustic", "power"], default="acoustic",
                         help="Quantity colouring the glowing ribbon: acoustic dBA (default) or electrical power W")
    p_build.add_argument("--glow-strength", type=float, default=None,
                         help="Emission strength of the glowing ribbon (default: 3.0; the plain ribbon uses 1.5)")
    p_build.add_argument("--glow-energy-vmin", type=float, default=None, help="Power trail color-scale floor in W (default: 0)")
    p_build.add_argument("--glow-energy-vmax", type=float, default=None, help="Power trail color-scale ceiling in W (default: 300)")
    p_build.add_argument("--glow-acoustic-vmin", type=float, default=None, help="Acoustic trail color-scale floor in dBA (default: 40)")
    p_build.add_argument("--glow-acoustic-vmax", type=float, default=None, help="Acoustic trail color-scale ceiling in dBA (default: 65)")
    p_build.add_argument("--acoustic", nargs="?", const=True, default=False, type=_bool_flag, help="Enable acoustics propagation floor material")
    p_build.add_argument(
        "--acoustic-mode",
        choices=["plain", "subtle", "glow", "additive"],
        default="plain",
        help="Acoustic floor rendering mode: plain (accurate non-reflective matte picture), subtle (gentle warm glow), glow (high-visibility emission), additive (white architectural floor with the field overlaid only where non-black)",
    )
    p_build.add_argument("--additive-start-dba", type=float, default=None,
                         help="Additive floor only: acoustic level (dBA) at which the field starts showing over the white floor (default: 45)")
    p_build.add_argument("--additive-full-dba", type=float, default=None,
                         help="Additive floor only: acoustic level (dBA) at which the field is fully shown (default: 55)")
    p_build.add_argument("--no-auto-texture", nargs="?", const=True, default=False, type=_bool_flag,
                         help="Do not generate the acoustic texture when it is missing; build without the acoustic floor instead")
    p_build.add_argument("--floor-brightness", type=float, default=None,
                         help="Albedo of the quiet floor in additive mode (default: 0.25). Raise towards 0.85 for a bright white floor; lower for more field colour")
    p_build.add_argument("--fill-light-strength", type=float, default=None,
                         help="Shadowless bounce fill sun energy (default: 0.6; 0 disables). Raise it if walls facing away from the sun read black, lower it if the scene is washed out")
    p_build.add_argument("--trajectory-thickness", type=float, default=0.04, help="Trajectory tube radius in metres")
    p_build.add_argument("--frame", type=int, default=None, help="Episode telemetry frame index (e.g. 621) or Blender animation frame")
    p_build.add_argument("--time", type=float, default=None, help="Episode relative time in seconds (e.g. 84.65)")
    p_build.add_argument("--scenario", help="Optional scenario name or path to scenario.yaml (e.g. fig4_office_desk_service)")

    # Subcommand: render
    p_render = subparsers.add_parser("render", help="Render an image from a camera preset in a .blend file")
    p_render.add_argument("--blend", required=True,
                          help="Path to a .blend file, or just its name (e.g. office_1_ep005_static) "
                               "to resolve it via --benchmark/--episode or the data directories")
    p_render.add_argument("--camera", default="Cam_TopDown_Full",
                          help="Camera name, a comma-separated list of names, or 'all' to render every camera "
                               "found in the .blend. Presets: Cam_TopDown_Full, Cam_TopDown, Cam_TopDown_Ward, "
                               "Cam_3Quarter_Hero, Cam_Corridor_EyeLevel")
    p_render.add_argument("--frame", type=int, default=None, help="Timeline frame to render (default: worst-case frame from scene)")
    p_render.add_argument("--output", "-o", default=None,
                          help="Output PNG path. Omit to write next to the .blend. With --camera all (or several "
                               "cameras) a directory is expected and a <blend>_<camera>.png suffix is added per camera")
    p_render.add_argument("--hud", nargs="?", const=True, default=False, type=_bool_flag, help="Generate and composite publication HUD card & colorbar onto the render")
    p_render.add_argument("--benchmark", help="Benchmark run name or path. Also used to resolve a bare --blend name. Required for --hud")
    p_render.add_argument("--episode", help="Episode ID (e.g. 005, episode_005). Also used to resolve a bare --blend name. Required for --hud")
    p_render.add_argument("--hud-pos", default="auto", choices=["auto", "top_left", "top_right", "bottom_left", "bottom_right"], help="Position of HUD overlay on rendered image (default: auto)")
    p_render.add_argument("--hud-scale", type=float, default=0.25, help="Width fraction of image for HUD card (default: 0.25)")
    p_render.add_argument("--resolution", "-r", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), help="Render image resolution in pixels (e.g. --resolution 3840 2160)")
    p_render.add_argument("--dpi", type=int, default=None, help="Target DPI scaling factor (scales base 2148x1400 relative to standard 300 DPI, e.g. --dpi 600 doubles resolution)")
    p_render.add_argument("--samples", "-s", type=int, default=None, help="Cycles render samples (e.g. 256, 512, 1024). Overrides scene default")
    p_render.add_argument("--percentage", type=int, default=None, help="Render scale percentage (e.g. 100, 150, 200)")

    # Subcommand: animate
    p_animate = subparsers.add_parser("animate", help="Render an animation frame sequence and mux it to MP4")
    p_animate.add_argument("--blend", required=True,
                           help="Path to a .blend file, or just its name (e.g. office_1_ep005) "
                                "to resolve it via --benchmark/--episode or the data directories")
    p_animate.add_argument("--benchmark", help="Benchmark run name or path, used to resolve a bare --blend name")
    p_animate.add_argument("--episode", help="Episode ID (e.g. 005, episode_005), used to resolve a bare --blend name")
    p_animate.add_argument("--camera", default="Cam_TopDown_Full",
                           help="Camera name, a comma-separated list of names, or 'all' to render every camera "
                                "found in the .blend (default: Cam_TopDown_Full)")
    p_animate.add_argument("--output", "-o", required=True, help="Output MP4 path. One MP4 is written per camera, each suffixed with the camera name")
    p_animate.add_argument("--start", type=int, default=None, help="First frame (default: 1)")
    p_animate.add_argument("--end", type=int, default=None, help="Last frame (default: scene.frame_end)")
    p_animate.add_argument("--stride", type=int, default=1, help="Render every Nth frame (default: 1; >1 gives a time-lapse preview)")
    p_animate.add_argument("--fps", type=float, default=30.0, help="Output playback fps (default: 30)")
    p_animate.add_argument("--resolution", "-r", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"),
                           help="Render image resolution in pixels (e.g. --resolution 1920 810)")
    p_animate.add_argument("--samples", "-s", type=int, default=None, help="Cycles render samples (e.g. 128, 256). Overrides scene default")
    p_animate.add_argument("--percentage", type=int, default=None, help="Render scale percentage (e.g. 100, 150, 200)")
    p_animate.add_argument("--crf", type=int, default=18, help="H.264 CRF quality for imageio-ffmpeg mux (default: 18)")
    p_animate.add_argument("--frames-dir", help="Directory for PNG frame files (default: <output>_frames next to the MP4). With several cameras each gets a <frames-dir>/<camera>/ subdirectory")
    p_animate.add_argument("--only-missing-frames", action="store_true",
                           help="Skip frames whose PNG already exists (resume interrupted render)")

    # Subcommand: hud
    p_hud = subparsers.add_parser("hud", help="Generate standalone HUD telemetry card, color scale, or composite onto image")
    p_hud.add_argument("--benchmark", required=True, help="Benchmark run name or path")
    p_hud.add_argument("--episode", required=True, help="Episode ID")
    p_hud.add_argument("--image", help="Optional rendered image to composite HUD onto")
    p_hud.add_argument("--pos", default="auto", choices=["auto", "top_left", "top_right", "bottom_left", "bottom_right"], help="Position on image (default: auto)")
    p_hud.add_argument("--scale", type=float, default=0.25, help="Width fraction of image for HUD card (default: 0.25)")
    p_hud.add_argument("--output", "-o", help="Output path for composited image or card")

    args = parser.parse_args(argv)
    if args.command == "build":
        cmd_build(args)
    elif args.command == "render":
        cmd_render(args)
    elif args.command == "animate":
        cmd_animate(args)
    elif args.command == "hud":
        cmd_hud(args)


if __name__ == "__main__":
    main()

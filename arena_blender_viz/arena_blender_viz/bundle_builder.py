"""
bundle_builder.py: Consolidates world geometry, cached 3D assets, and episode
telemetry into a single scene_bundle.json file consumed by Blender.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_converter import ModelConverter
from .telemetry_extractor import TelemetryExtractor
from .world_parser import WorldDef, parse_world_yaml


class BundleBuilder:
    def __init__(
        self,
        world_yaml_path: Path,
        benchmark_episode_dir: Path | None = None,
        acoustic_overlay_png: Path | None = None,
        options: dict[str, Any] | None = None,
    ):
        self.world_yaml_path = Path(world_yaml_path)
        self.benchmark_episode_dir = Path(benchmark_episode_dir) if benchmark_episode_dir else None
        self.acoustic_overlay_png = Path(acoustic_overlay_png) if acoustic_overlay_png else None
        self.options = options or {}

    def build_bundle(self, output_json_path: Path) -> dict[str, Any]:
        """Build the full scene bundle and write to JSON."""
        # 1. Parse World
        world: WorldDef = parse_world_yaml(self.world_yaml_path)

        # 2. Batch convert models
        all_model_ids = [
            entity.model_id
            for zone in world.zones
            for entity in zone.static_entities
            if entity.model_id
        ]
        # Ensure pedestrian human models are always converted and available
        for h_id in ["Common/Human/arenian", "Common/Human/arenian_seated", "arenian", "arenian_seated"]:
            if h_id not in all_model_ids:
                all_model_ids.append(h_id)

        converter = ModelConverter()
        model_glb_map = converter.batch_convert_models(all_model_ids)

        # 3. Telemetry and Scenario Entities (optional)
        robot_trajectory: list[dict[str, Any]] = []
        door_timelines: dict[str, list[dict[str, Any]]] = {}
        pedestrians: list[dict[str, Any]] = []
        encounters: list[dict[str, Any]] = []
        worst_case_frame: dict[str, Any] | None = None
        pedestrian_models: dict[str, str] = {}  # pid str -> model name, e.g. "2": "arenian_seated"

        # Resolve scenario YAML if present
        scenario_yaml_path: Path | None = None
        if self.options.get("scenario"):
            cand = Path(self.options["scenario"])
            if cand.is_file():
                scenario_yaml_path = cand
        if not scenario_yaml_path and self.benchmark_episode_dir:
            manifest_file = self.benchmark_episode_dir.parent.parent / "manifest.yaml"
            if manifest_file.is_file():
                try:
                    import yaml
                    with open(manifest_file, "r", encoding="utf-8") as mf:
                        mdata = yaml.safe_load(mf) or {}
                    stages = mdata.get("suite", {}).get("stages", [])
                    for st in stages:
                        sc_file = st.get("config", {}).get("scenario", {}).get("file")
                        if sc_file:
                            world_dir = self.world_yaml_path.parent if self.world_yaml_path.parent.name != "0" else self.world_yaml_path.parent.parent
                            for sc_cand in [
                                world_dir / "scenarios" / sc_file / "scenario.yaml",
                                world_dir / "scenarios" / f"{sc_file}.yaml",
                                world_dir / "scenarios" / sc_file,
                            ]:
                                if sc_cand.is_file():
                                    scenario_yaml_path = sc_cand
                                    break
                        if scenario_yaml_path:
                            break
                except Exception:
                    pass

        # If not from manifest, check if world has default or matching scenario
        if not scenario_yaml_path:
            world_dir = self.world_yaml_path.parent if self.world_yaml_path.parent.name != "0" else self.world_yaml_path.parent.parent
            def_sc = world_dir / "scenarios" / "default" / "scenario.yaml"
            if def_sc.is_file():
                scenario_yaml_path = def_sc

        scenario_static_peds: list[dict[str, Any]] = []
        if scenario_yaml_path and scenario_yaml_path.is_file():
            try:
                import yaml
                with open(scenario_yaml_path, "r", encoding="utf-8") as sf:
                    sdata = yaml.safe_load(sf) or {}
                dyn_list = sdata.get("dynamic", [])
                for idx, d_ent in enumerate(dyn_list):
                    m_name = d_ent.get("model", "arenian")
                    pedestrian_models[str(idx)] = m_name
                    if m_name and m_name not in all_model_ids:
                        all_model_ids.append(m_name)

                # Also collect static scenario pedestrians (e.g. seated observers, patrons)
                stat_list = sdata.get("static", [])
                for s_idx, s_ent in enumerate(stat_list):
                    m_name = s_ent.get("model", "")
                    if "arenian" in m_name or "ped" in s_ent.get("name", "").lower() or "mic" in s_ent.get("name", "").lower():
                        pos = s_ent.get("pose") or s_ent.get("position") or [0.0, 0.0, 0.0]
                        sx = float(pos[0]) if len(pos) > 0 else 0.0
                        sy = float(pos[1]) if len(pos) > 1 else 0.0
                        syaw = float(pos[2]) if len(pos) > 2 else 0.0
                        pid_key = f"static_{s_idx}"
                        pedestrian_models[pid_key] = m_name or "arenian_seated"
                        if m_name and m_name not in all_model_ids:
                            all_model_ids.append(m_name)
                        scenario_static_peds.append({
                            "id": pid_key,
                            "x": round(sx, 3),
                            "y": round(sy, 3),
                            "yaw": round(syaw, 4),
                        })

                print(f"[Arena Blender Viz] Loaded scenario pedestrian mapping from {scenario_yaml_path.name}: {pedestrian_models}")
            except Exception as e:
                print(f"[!] Warning reading scenario {scenario_yaml_path}: {e}")

        if self.benchmark_episode_dir and self.benchmark_episode_dir.is_dir():
            extractor = TelemetryExtractor(self.benchmark_episode_dir)
            robot_trajectory = extractor.extract_robot_trajectory()
            door_timelines = extractor.extract_door_timelines()
            pedestrians = extractor.extract_pedestrians()

            # Supplement telemetry frames with scenario static pedestrians if present
            if scenario_static_peds:
                if not pedestrians:
                    pedestrians = [{"t": 0.0, "peds": scenario_static_peds}]
                else:
                    for fr in pedestrians:
                        fr["peds"].extend(scenario_static_peds)

            encounters = extractor.compute_encounters(robot_trajectory, pedestrians)

            # Resolve active/worst-case frame: explicit option first, then combined_metrics fallback
            fps = self.options.get("fps", 30)
            explicit_time = self.options.get("time")
            explicit_frame = self.options.get("frame")

            if explicit_time is not None and robot_trajectory:
                t_sec = float(explicit_time)
                closest = min(robot_trajectory, key=lambda p: abs(p["t"] - t_sec))
                frame_idx = max(1, int(closest["t"] * fps))
                worst_case_frame = {
                    "robot_x": closest["x"],
                    "robot_y": closest["y"],
                    "robot_yaw": closest.get("yaw", 0.0),
                    "t": closest["t"],
                    "frame": frame_idx,
                    "source_dba": closest.get("acoustic_dba", 100.0),
                }
            elif explicit_frame is not None and robot_trajectory:
                f_val = int(explicit_frame)
                if f_val < len(robot_trajectory):
                    # Telemetry row index (e.g. 621)
                    pt = robot_trajectory[f_val]
                    frame_idx = max(1, int(pt["t"] * fps))
                    worst_case_frame = {
                        "robot_x": pt["x"],
                        "robot_y": pt["y"],
                        "robot_yaw": pt.get("yaw", 0.0),
                        "t": pt["t"],
                        "frame": frame_idx,
                        "source_dba": pt.get("acoustic_dba", 100.0),
                    }
                else:
                    # Blender timeline animation frame (e.g. 2540)
                    t_sec = f_val / fps
                    closest = min(robot_trajectory, key=lambda p: abs(p["t"] - t_sec))
                    worst_case_frame = {
                        "robot_x": closest["x"],
                        "robot_y": closest["y"],
                        "robot_yaw": closest.get("yaw", 0.0),
                        "t": closest["t"],
                        "frame": f_val,
                        "source_dba": closest.get("acoustic_dba", 100.0),
                    }
            else:
                # Extract worst-case acoustic frame from combined_metrics.parquet
                cm_file = self.benchmark_episode_dir.parent.parent / "combined_metrics.parquet"
                if cm_file.is_file():
                    try:
                        import polars as pl
                        ep_num = int(self.benchmark_episode_dir.name.replace("episode_", ""))
                        df = pl.read_parquet(cm_file)
                        match = df.filter(pl.col("episode") == ep_num)
                        if match.height > 0:
                            wf = match.to_dicts()[0].get("worst_case_acoustic_frame")
                            if wf:
                                if isinstance(wf, str):
                                    wf = json.loads(wf)
                                rx = wf.get("robot_x")
                                ry = wf.get("robot_y")
                                ryaw = 0.0
                                t_sec = 0.0
                                frame_idx = 1
                                if rx is not None and ry is not None and robot_trajectory:
                                    closest = min(robot_trajectory, key=lambda p: (p["x"] - rx)**2 + (p["y"] - ry)**2)
                                    ryaw = closest.get("yaw", 0.0)
                                    t_sec = closest.get("t", 0.0)
                                    frame_idx = max(1, int(t_sec * fps))
                                worst_case_frame = {
                                    "robot_x": rx,
                                    "robot_y": ry,
                                    "robot_yaw": ryaw,
                                    "t": t_sec,
                                    "frame": frame_idx,
                                    "source_dba": wf.get("source_dba", 100.0),
                                }
                    except Exception as e:
                        pass

            # Auto-resolve acoustic snapshot from benchmark plots if not explicitly specified
            if not self.acoustic_overlay_png and self.options.get("acoustic", False):
                plots_dir = self.benchmark_episode_dir.parent.parent / "plots"
                ep_name = self.benchmark_episode_dir.name
                for cand in [
                    plots_dir / f"{ep_name}_acoustic_raw.mp4",
                    plots_dir / f"{ep_name}_acoustic_snapshot_raw.png",
                    plots_dir / f"{ep_name}_acoustic_snapshot.png",
                    plots_dir / "acoustic_field_spatial_snapshot_raw.png",
                    plots_dir / "acoustic_field_spatial_snapshot.png",
                ]:
                    if cand.is_file():
                        self.acoustic_overlay_png = cand
                        break

        # Register Jackal UGV model GLB if available
        jackal_glb = converter.cache_dir / "jackal_robot.glb"
        if not jackal_glb.is_file():
            jackal_glb = Path(__file__).parent.parent / ".cache" / "glb" / "jackal_robot.glb"
        if jackal_glb.is_file():
            model_glb_map["robot/jackal"] = str(jackal_glb).replace("\\", "/")

        # 4. Assemble Bundle Dictionary
        bundle: dict[str, Any] = {
            "world": world.to_dict(),
            "model_glbs": model_glb_map,
            "telemetry": {
                "robot_trajectory": robot_trajectory,
                "door_timelines": door_timelines,
                "pedestrians": pedestrians,
                "encounters": encounters,
                "worst_case_frame": worst_case_frame,
                "pedestrian_models": pedestrian_models,
            },
            "options": {
                "animate_doors": self.options.get("animate_doors", True),
                "animate_peds": self.options.get("animate_peds", True),
                "show_door_radius": self.options.get("show_door_radius", False),
                "show_encounters": self.options.get("show_encounters", False),
                "show_zone_overlays": self.options.get("show_zone_overlays", False),
                "show_energy_glow": self.options.get("show_energy_glow", False),
                "glow_energy_vmin": self.options.get("glow_energy_vmin") or 0.0,
                "glow_energy_vmax": self.options.get("glow_energy_vmax") or 300.0,
                "glow_acoustic_vmin": self.options.get("glow_acoustic_vmin") or 40.0,
                "glow_acoustic_vmax": self.options.get("glow_acoustic_vmax") or 65.0,
                "trajectory_thickness": self.options.get("trajectory_thickness", 0.04),
                "fps": self.options.get("fps", 30),
                "acoustic_mode": self.options.get("acoustic_mode", "plain"),
            },
            "acoustic_overlay": {
                "png_path": str(self.acoustic_overlay_png).replace("\\", "/")
                if self.acoustic_overlay_png and self.acoustic_overlay_png.is_file()
                else None,
                "bounds": list(world.bounds),
            },
        }

        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        return bundle

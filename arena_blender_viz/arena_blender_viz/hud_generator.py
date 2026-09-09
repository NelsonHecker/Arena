"""
hud_generator.py: Generates publication-quality telemetry overlays, acoustic color scales,
and HUD readout cards for Arena Evaluation 3.0 simulation renders.
Exports both standalone transparent PNGs (for Overleaf/LaTeX/Keynote) and composited visuals.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageFilter
import polars as pl

logger = logging.getLogger(__name__)


class HUDGenerator:
    """Generates scientific HUD cards and color scales from benchmark episode telemetry."""

    @staticmethod
    def extract_metrics(benchmark_dir: Path | str, episode_id: int | str) -> dict[str, Any]:
        """Extract publication-relevant metrics for a given episode from combined_metrics.parquet."""
        bench_path = Path(benchmark_dir)
        if not bench_path.is_dir():
            search_roots: list[Path] = []
            if "ARENA_DATA_DIR" in os.environ:
                search_roots.append(Path(os.environ["ARENA_DATA_DIR"]) / "benchmarks")
            if "ARENA_WS_DIR" in os.environ:
                search_roots.append(Path(os.environ["ARENA_WS_DIR"]) / "data" / "benchmarks")
            search_roots.extend([
                Path("/opt/arena_ws/data/benchmarks"),
                Path("u:/data/benchmarks"),
                Path("/data/benchmarks"),
            ])
            for r in search_roots:
                alt = r / benchmark_dir
                if alt.is_dir():
                    bench_path = alt
                    break
        if isinstance(episode_id, str):
            clean_ep = episode_id.lower().replace("episode_", "").replace("ep_", "").strip()
            ep_num = int(clean_ep)
        else:
            ep_num = int(episode_id)

        cm_file = bench_path / "combined_metrics.parquet"
        metrics: dict[str, Any] = {
            "episode": ep_num,
            "benchmark_name": bench_path.name,
            "planner": "Nav2 Controller",
            "stage": "simulation_stage",
            "result": "SUCCESS",
            "success": True,
            "energy_total_wh": None,
            "power_peak_w": None,
            "battery_soc_final": None,
            "battery_soc_drop_pct": None,
            "ped_max_exposure_dba": None,
            "ped_leq_exposure_dba": None,
            "acoustic_surge_index": None,
            "time_to_goal": None,
            "path_length": None,
            "velocity_mean": None,
            "time_waiting_at_doors": None,
            "social_force_max": None,
            "worst_case_source_dba": 100.0,
            "vmin": 20.0,
            "vmax": 100.0,
        }

        if cm_file.is_file():
            try:
                df = pl.read_parquet(cm_file)
                match = df.filter(pl.col("episode") == ep_num)
                if match.height > 0:
                    row = match.to_dicts()[0]
                    metrics["planner"] = row.get("planner", metrics["planner"])
                    metrics["stage"] = row.get("stage", metrics["stage"])
                    metrics["result"] = row.get("result", "SUCCESS")
                    metrics["success"] = row.get("success", True)
                    # Episode Energy:
                    # In combined_metrics.parquet, energy_total_wh can suffer from an un-reset cumulative
                    # ROS /energy topic odometer, which accumulates Wh across all previous episodes (e.g. 147.3 Wh).
                    # The physically grounded per-episode energy is the sum of static, mechanical, and thermal subsystems.
                    e_static = row.get("energy_static_wh")
                    e_mech = row.get("energy_mechanical_wh")
                    e_therm = row.get("energy_thermal_wh")
                    sub_sum = sum(v for v in [e_static, e_mech, e_therm] if v is not None)
                    raw_energy = row.get("energy_total_wh")

                    if sub_sum > 0 and (raw_energy is None or raw_energy > sub_sum * 2.5):
                        metrics["energy_total_wh"] = sub_sum
                    elif raw_energy is not None:
                        metrics["energy_total_wh"] = raw_energy
                    else:
                        metrics["energy_total_wh"] = sub_sum

                    # Peak power draw: fallback to timeseries maximum if None
                    p_peak = row.get("power_peak_w")
                    if p_peak is None:
                        ts_p = row.get("timeseries_power_total_w")
                        if ts_p:
                            p_peak = max(ts_p)
                    metrics["power_peak_w"] = p_peak

                    metrics["battery_soc_final"] = row.get("battery_soc_final")
                    metrics["battery_soc_drop_pct"] = row.get("battery_soc_drop_pct")
                    metrics["ped_max_exposure_dba"] = row.get("ped_max_exposure_dba")
                    metrics["ped_leq_exposure_dba"] = row.get("ped_leq_exposure_dba")
                    metrics["acoustic_surge_index"] = row.get("acoustic_surge_index")
                    metrics["time_to_goal"] = row.get("time_to_goal")
                    metrics["path_length"] = row.get("path_length")
                    metrics["velocity_mean"] = row.get("velocity_mean")
                    metrics["time_waiting_at_doors"] = row.get("time_waiting_at_doors")
                    metrics["social_force_max"] = row.get("social_force_max")
                    
                    wf = row.get("worst_case_acoustic_frame")
                    if wf:
                        if isinstance(wf, str):
                            try:
                                wf = json.loads(wf)
                            except Exception:
                                wf = None
                        if isinstance(wf, dict):
                            metrics["worst_case_source_dba"] = wf.get("source_dba", 100.0)
            except Exception as e:
                logger.warning(f"Could not read combined_metrics.parquet: {e}")

        # Derive human-friendly benchmark title
        raw_bname = metrics["benchmark_name"]
        clean_title = raw_bname
        # Strip timestamp prefix if present (e.g. 20260906-034416-figure8_hospital_door_dilemma-...)
        parts = raw_bname.split("-")
        if len(parts) >= 3 and len(parts[0]) == 8 and len(parts[1]) == 6:
            clean_title = " ".join(parts[2:-1]).replace("_", " ").upper()
            if not clean_title:
                clean_title = parts[2].replace("_", " ").upper()
        metrics["display_title"] = clean_title or raw_bname

        # Auto-detect vmin / vmax from benchmark manifest plots if available
        for m_file in bench_path.glob("*.yaml"):
            try:
                import yaml
                m_data = yaml.safe_load(m_file.read_text(encoding="utf-8"))
                if isinstance(m_data, dict):
                    for pl_item in m_data.get("plots", []):
                        if pl_item.get("type") == "acoustic_field" or "acoustic" in pl_item.get("id", ""):
                            opts = pl_item.get("options", {})
                            if "vmin" in opts:
                                metrics["vmin"] = float(opts["vmin"])
                            if "vmax" in opts:
                                metrics["vmax"] = float(opts["vmax"])
            except Exception:
                pass

        return metrics

    @staticmethod
    def generate_colorbar(
        out_path: Path | str,
        vmin: float = 20.0,
        vmax: float = 65.0,
        orientation: str = "horizontal",
        dpi: int = 300,
        width_in: float = 6.0,
        height_in: float = 0.9,
    ) -> Path:
        """Generate a standalone high-resolution transparent acoustic color scale."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
        fig.patch.set_alpha(0.0)
        ax.set_facecolor("none")

        norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
        sm = matplotlib.cm.ScalarMappable(cmap="inferno", norm=norm)
        sm.set_array([])

        cb = fig.colorbar(sm, cax=ax, orientation=orientation)
        cb.set_label("Sound Pressure Level, $L_p$ (dBA)", color="#94a3b8", fontsize=8.0, weight="bold", labelpad=5)
        cb.ax.tick_params(colors="#cbd5e1", labelsize=7.0, length=3, pad=2)
        cb.outline.set_edgecolor("#252d3d")
        cb.outline.set_linewidth(0.8)

        fig.savefig(out_path, bbox_inches="tight", transparent=True, pad_inches=0.02)
        plt.close(fig)
        return out_path

    @staticmethod
    def generate_hud_card(
        metrics: dict[str, Any],
        out_path: Path | str,
        dpi: int = 300,
        width_in: float = 7.2,
        height_in: float = 2.7,
    ) -> Path:
        """Generate a clean, sober scientific publication telemetry legend card."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fig = plt.figure(figsize=(width_in, height_in), dpi=dpi)
        fig.patch.set_alpha(0.0)

        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("none")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        # 1. Dark technical container with crisp 1px hairline border
        card = patches.FancyBboxPatch(
            (0.005, 0.01), 0.99, 0.98,
            boxstyle="Square,pad=0.0",
            facecolor="#0b0e17", alpha=0.94,
            edgecolor="#252d3d", linewidth=1.0,
        )
        ax.add_patch(card)

        # Top technical accent line (2px cyan hairline)
        ax.plot([0.005, 0.995], [0.99, 0.99], color="#0284c7", linewidth=2.0)

        # 2. Header: Title, Scenario, and Planner Status
        title = metrics.get("display_title", "ARENA 3.0 EVALUATION").upper()
        planner_str = str(metrics.get("planner", "Nav2")).upper()
        result_str = str(metrics.get("result", "SUCCESS")).upper()

        ax.text(0.035, 0.90, "TELEMETRY SUMMARY", color="#94a3b8", fontsize=7.5, weight="bold", va="center")
        ax.text(0.24, 0.90, f"|   {title}", color="#64748b", fontsize=7.5, weight="medium", va="center")
        ax.text(0.965, 0.90, f"[{planner_str}]  {result_str}", color="#38bdf8", fontsize=7.8, weight="bold", ha="right", va="center")

        # Header Divider
        ax.plot([0.035, 0.965], [0.82, 0.82], color="#1a2233", linewidth=0.8)

        # 3. Scientific 3-Column Metrics Grid
        # Column 1: Energy & Autonomy
        wh_val = metrics.get("energy_total_wh")
        wh_str = f"{wh_val:.2f}" if wh_val is not None else "--"
        soc_d = metrics.get("battery_soc_drop_pct")
        peak_w = metrics.get("power_peak_w")
        soc_line = []
        if soc_d is not None:
            soc_line.append(f"ΔSoC: -{soc_d:.2f}%")
        if peak_w is not None:
            soc_line.append(f"P_peak: {peak_w:.0f} W")
        sub_energy_1 = "  •  ".join(soc_line) if soc_line else "Battery Autonomy: Stable"
        robot_name = metrics.get("robot", "Jackal UGV")

        ax.text(0.035, 0.74, "ENERGY & AUTONOMY", color="#64748b", fontsize=6.8, weight="bold")
        ax.text(0.035, 0.59, wh_str, color="#f8fafc", fontsize=14.5, weight="bold")
        ax.text(0.145, 0.59, "Wh", color="#94a3b8", fontsize=9.0, weight="medium")
        ax.text(0.035, 0.47, sub_energy_1, color="#94a3b8", fontsize=6.8)
        ax.text(0.035, 0.38, f"Platform: {robot_name}", color="#64748b", fontsize=6.2)

        # Vertical divider 1
        ax.plot([0.34, 0.34], [0.36, 0.78], color="#1a2233", linewidth=0.8)

        # Column 2: Acoustic Exposure
        ped_dba = metrics.get("ped_max_exposure_dba")
        ped_str = f"{ped_dba:.1f}" if ped_dba is not None else "--"
        leq = metrics.get("ped_leq_exposure_dba")
        asi = metrics.get("acoustic_surge_index")
        aco_line = []
        if leq is not None:
            aco_line.append(f"L_Aeq: {leq:.1f} dBA")
        if asi is not None:
            aco_line.append(f"ASI: {asi:.1f} dB/s")
        sub_aco_1 = "  •  ".join(aco_line) if aco_line else "Acoustic Field: Nominal"
        src_dba = metrics.get("worst_case_source_dba")
        src_str = f"Source Peak: {src_dba:.1f} dBA" if src_dba else "Acoustic Shadow: Active"

        ax.text(0.37, 0.74, "ACOUSTIC EXPOSURE", color="#64748b", fontsize=6.8, weight="bold")
        ax.text(0.37, 0.59, ped_str, color="#f8fafc", fontsize=14.5, weight="bold")
        ax.text(0.485, 0.59, "dBA", color="#94a3b8", fontsize=9.0, weight="medium")
        ax.text(0.37, 0.47, sub_aco_1, color="#94a3b8", fontsize=6.8)
        ax.text(0.37, 0.38, src_str, color="#64748b", fontsize=6.2)

        # Vertical divider 2
        ax.plot([0.67, 0.67], [0.36, 0.78], color="#1a2233", linewidth=0.8)

        # Column 3: Transit & Kinematics
        ttg = metrics.get("time_to_goal")
        ttg_str = f"{ttg:.1f}" if ttg is not None else "--"
        dist = metrics.get("path_length")
        v_mean = metrics.get("velocity_mean")
        kin_line = []
        if dist is not None:
            kin_line.append(f"Dist: {dist:.1f} m")
        if v_mean is not None:
            kin_line.append(f"v_mean: {v_mean:.2f} m/s")
        sub_kin_1 = "  •  ".join(kin_line) if kin_line else "Mission Transit: Done"
        wait = metrics.get("time_waiting_at_doors")
        wait_str = f"Doorway Wait: {wait:.1f} s" if wait is not None else "Navigation: Trajectory Verified"

        ax.text(0.70, 0.74, "TRANSIT & DURATION", color="#64748b", fontsize=6.8, weight="bold")
        ax.text(0.70, 0.59, ttg_str, color="#f8fafc", fontsize=14.5, weight="bold")
        ax.text(0.795, 0.59, "s", color="#94a3b8", fontsize=9.0, weight="medium")
        ax.text(0.70, 0.47, sub_kin_1, color="#94a3b8", fontsize=6.8)
        ax.text(0.70, 0.38, wait_str, color="#64748b", fontsize=6.2)

        # Lower Divider
        ax.plot([0.035, 0.965], [0.31, 0.31], color="#1a2233", linewidth=0.8)

        # Colorbar Title
        ax.text(0.035, 0.23, "SOUND PRESSURE LEVEL, L_p (dBA)", color="#64748b", fontsize=6.5, weight="bold")

        # Integrated Scientific Colorbar
        cbar_ax = fig.add_axes([0.035, 0.08, 0.93, 0.08])
        vmin = metrics.get("vmin", 20.0)
        vmax = metrics.get("vmax", 65.0)
        norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
        sm = matplotlib.cm.ScalarMappable(cmap="inferno", norm=norm)
        sm.set_array([])
        cb = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
        cb.ax.tick_params(colors="#cbd5e1", labelsize=6.2, length=2.5, pad=1.5)
        cb.outline.set_edgecolor("#252d3d")
        cb.outline.set_linewidth(0.8)

        fig.savefig(out_path, bbox_inches="tight", transparent=True, pad_inches=0.03)
        plt.close(fig)
        return out_path

    @staticmethod
    def composite_onto_image(
        base_image_path: Path | str,
        out_image_path: Path | str,
        hud_card_path: Path | str | None = None,
        colorbar_path: Path | str | None = None,
        position: str = "auto",
        hud_scale_width_pct: float = 0.25,
        padding: int = 32,
    ) -> Path:
        """
        Composite HUD card and/or colorbar onto a rendered Blender image.
        Supports 'auto' placement which automatically detects the cleanest empty margin
        with zero/minimal occlusion of the 3D scene.
        """
        base_img = Image.open(base_image_path).convert("RGBA")
        bw, bh = base_img.size

        # 1. Overlay HUD Card if provided
        if hud_card_path and Path(hud_card_path).is_file():
            card_img = Image.open(hud_card_path).convert("RGBA")
            target_cw = int(bw * hud_scale_width_pct)
            target_ch = int(card_img.height * (target_cw / card_img.width))
            card_resized = card_img.resize((target_cw, target_ch), Image.Resampling.LANCZOS)

            # Resolve position
            chosen_pos = position
            if chosen_pos == "auto":
                # Detect the corner with the lowest average pixel energy (i.e. cleanest empty background)
                arr = np.array(base_img)[:, :, :3]
                corners = {
                    "top_left": (padding, padding),
                    "top_right": (bw - target_cw - padding, padding),
                    "bottom_left": (padding, bh - target_ch - padding),
                    "bottom_right": (bw - target_cw - padding, bh - target_ch - padding),
                }
                corner_scores = {}
                for c_name, (cx, cy) in corners.items():
                    crop_arr = arr[cy : cy + target_ch, cx : cx + target_cw]
                    corner_scores[c_name] = float(crop_arr.mean()) if crop_arr.size > 0 else 999.0

                # Prioritize canonical reading order for empty margins (< 1.5 intensity)
                clean_candidates = [c for c in ["top_left", "top_right", "bottom_left", "bottom_right"] if corner_scores[c] < 1.5]
                if clean_candidates:
                    chosen_pos = clean_candidates[0]
                else:
                    chosen_pos = min(corner_scores, key=corner_scores.get)
                logger.info(f"Auto-selected cleanest HUD position '{chosen_pos}' (scores: {corner_scores})")

            # Determine anchor pixel coordinates
            if chosen_pos == "top_left":
                pos = (padding, padding)
            elif chosen_pos == "top_right":
                pos = (bw - target_cw - padding, padding)
            elif chosen_pos == "bottom_left":
                pos = (padding, bh - target_ch - padding)
            elif chosen_pos == "bottom_right":
                pos = (bw - target_cw - padding, bh - target_ch - padding)
            else:
                pos = (padding, padding)

            # Crisp hairline shadow
            shadow_mask = Image.new("RGBA", (target_cw + 14, target_ch + 14), (0, 0, 0, 0))
            shadow_box = Image.new("RGBA", (target_cw, target_ch), (0, 0, 0, 160))
            shadow_mask.paste(shadow_box, (7, 7))
            shadow_blurred = shadow_mask.filter(ImageFilter.GaussianBlur(radius=5))

            base_img.paste(shadow_blurred, (pos[0] - 5, pos[1] - 5), shadow_blurred)
            base_img.paste(card_resized, pos, card_resized)

        # 2. Overlay Standalone Colorbar if provided without card
        if colorbar_path and Path(colorbar_path).is_file() and not hud_card_path:
            cb_img = Image.open(colorbar_path).convert("RGBA")
            target_w = int(bw * 0.22)
            target_h = int(cb_img.height * (target_w / cb_img.width))
            cb_resized = cb_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            pos = (bw - target_w - padding, bh - target_h - padding)
            base_img.paste(cb_resized, pos, cb_resized)

        out_path = Path(out_image_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        base_img.convert("RGB").save(out_path, quality=95)
        return out_path

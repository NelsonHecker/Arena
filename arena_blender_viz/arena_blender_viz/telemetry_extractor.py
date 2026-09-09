"""
telemetry_extractor.py: Ingests benchmark episode Parquet telemetry.
Extracts robot trajectories, dynamic pedestrian paths, sliding door animations,
instantaneous power/energy, and proxemic encounter events using Polars.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)


class TelemetryExtractor:
    def __init__(self, episode_dir: Path):
        self.episode_dir = Path(episode_dir)
        self.topics_dir = self.episode_dir / "topics"
        if not self.topics_dir.is_dir():
            # Sometimes parquet files are directly in episode_dir
            self.topics_dir = self.episode_dir
        self._t0_ns: int | None = None

    def find_robot_topics_dir(self) -> Path | None:
        """Find the robot namespace directory (e.g. env_0_jackal, jackal, etc.)."""
        # Look for subdirectories containing tf_gt.parquet
        for p in self.topics_dir.glob("*/tf_gt.parquet"):
            return p.parent
        # Look for direct tf_gt.parquet
        if (self.topics_dir / "tf_gt.parquet").is_file():
            return self.topics_dir
        return None

    def get_episode_t0_ns(self) -> int:
        """Obtain single synchronized episode start timestamp in nanoseconds."""
        if self._t0_ns is not None:
            return self._t0_ns

        # 1. First priority: Robot ground-truth odometry
        robot_dir = self.find_robot_topics_dir()
        if robot_dir:
            tf_file = robot_dir / "tf_gt.parquet"
            if tf_file.is_file():
                try:
                    self._t0_ns = int(pl.read_parquet(tf_file)["time_ns"].min())
                    return self._t0_ns
                except Exception:
                    pass

        # 2. Fallback: Semantic snapshot or any topic file
        for fname in ["semantic_snapshot.parquet", "peds.parquet", "tf.parquet"]:
            p = self.topics_dir / fname
            if p.is_file():
                try:
                    val = pl.read_parquet(p).select("time_ns").min().item()
                    if val is not None:
                        self._t0_ns = int(val)
                        return self._t0_ns
                except Exception:
                    pass

        self._t0_ns = 0
        return self._t0_ns

    def extract_robot_trajectory(self) -> list[dict[str, Any]]:
        """Extract robot trajectory from tf_gt.parquet and join with power/acoustics."""
        robot_dir = self.find_robot_topics_dir()
        if robot_dir is None:
            logger.warning(f"No robot topics found in {self.topics_dir}")
            return []

        tf_file = robot_dir / "tf_gt.parquet"
        if not tf_file.is_file():
            return []

        tf_df = pl.read_parquet(tf_file)
        # Select required columns
        req_cols = ["time_ns", "pos_x_gt", "pos_y_gt", "yaw_gt"]
        tf_df = tf_df.select([c for c in req_cols if c in tf_df.columns])

        # Optional join with power
        pwr_file = robot_dir / "power.parquet"
        if pwr_file.is_file():
            try:
                pwr_df = pl.read_parquet(pwr_file).select(["time_ns", "total_power_w"])
                tf_df = tf_df.join_asof(pwr_df, on="time_ns", strategy="nearest")
            except Exception as e:
                logger.debug(f"Could not join power.parquet: {e}")

        # Optional join with acoustics
        aco_file = robot_dir / "acoustics.parquet"
        if aco_file.is_file():
            try:
                aco_df = pl.read_parquet(aco_file).select(["time_ns", "total_level_af_dba"])
                tf_df = tf_df.join_asof(aco_df, on="time_ns", strategy="nearest")
            except Exception as e:
                logger.debug(f"Could not join acoustics.parquet: {e}")

        # Synchronized relative timestamps in seconds from episode start
        t0 = self.get_episode_t0_ns()
        trajectory: list[dict[str, Any]] = []

        for row in tf_df.iter_rows(named=True):
            t_sec = max(0.0, (row["time_ns"] - t0) / 1e9)
            trajectory.append({
                "t": round(t_sec, 3),
                "x": round(float(row.get("pos_x_gt", 0.0)), 3),
                "y": round(float(row.get("pos_y_gt", 0.0)), 3),
                "yaw": round(float(row.get("yaw_gt", 0.0)), 4),
                "power_w": round(float(row.get("total_power_w", 0.0) or 0.0), 1),
                "acoustic_dba": round(float(row.get("total_level_af_dba", 0.0) or 0.0), 1),
            })

        return trajectory

    def extract_door_timelines(self) -> dict[str, list[dict[str, Any]]]:
        """
        Extract sliding door state and opening progress timeline.
        Returns: {door_name: [{"t": sec, "progress": 0.0_to_1.0, "open": bool}]}
        """
        sem_file = self.topics_dir / "semantic_snapshot.parquet"
        if not sem_file.is_file():
            return {}

        try:
            df = pl.read_parquet(sem_file)
            if "field" not in df.columns or "entity" not in df.columns:
                return {}

            t0 = self.get_episode_t0_ns()
            # Only use numeric 'progress' field to prevent boolean 'open' from corrupting interpolation
            door_df = df.filter(pl.col("field") == "progress")

            timelines: dict[str, list[dict[str, Any]]] = {}

            # Group by entity (door name)
            for entity_name, group in door_df.group_by("entity"):
                raw_ent = str(entity_name[0] if isinstance(entity_name, tuple) else entity_name)
                name_parts = raw_ent.split("/")
                clean_name = name_parts[1] if len(name_parts) >= 2 else name_parts[0]

                # Extract deduplicated (t, progress) pairs
                raw_entries: list[tuple[float, float]] = []
                for row in group.sort("time_ns").iter_rows(named=True):
                    t_sec = round(max(0.0, (row["time_ns"] - t0) / 1e9), 3)
                    val_num = float(row.get("value_num") or 0.0)
                    if not raw_entries or raw_entries[-1][0] != t_sec:
                        raw_entries.append((t_sec, val_num))

                # Insert hold entries for latched state periods so doors stay open/closed without drifting
                held_entries: list[tuple[float, float]] = []
                for i in range(len(raw_entries)):
                    t, p = raw_entries[i]
                    held_entries.append((t, p))
                    if i < len(raw_entries) - 1:
                        next_t, _ = raw_entries[i + 1]
                        if next_t - t > 0.2:
                            held_entries.append((round(next_t - 0.05, 3), p))

                timeline_entries = [
                    {
                        "t": t,
                        "progress": round(p, 4),
                        "open": p > 0.1,
                    }
                    for t, p in held_entries
                ]

                timelines[clean_name] = timeline_entries
                # Also store with/without 'door_' prefix for universal matching
                if clean_name.startswith("door_"):
                    timelines[clean_name.replace("door_", "")] = timeline_entries
                else:
                    timelines[f"door_{clean_name}"] = timeline_entries

            return timelines
        except Exception as e:
            logger.warning(f"Failed to extract door timelines: {e}")
            return {}

    def extract_pedestrians(self) -> list[dict[str, Any]]:
        """
        Extract dynamic pedestrian positions and headings over time from peds.parquet.
        Returns list of frames: [{"t": sec, "peds": [{"x": x, "y": y, "yaw": yaw}, ...]}]
        """
        peds_file = self.topics_dir / "peds.parquet"
        if not peds_file.is_file():
            return []

        try:
            df = pl.read_parquet(peds_file)
            t0 = self.get_episode_t0_ns()
            frames: list[dict[str, Any]] = []

            for row in df.sort("time_ns").iter_rows(named=True):
                t_sec = max(0.0, (row["time_ns"] - t0) / 1e9)
                pos_list = row.get("peds_positions") or []
                yaw_list = row.get("peds_headings") or []

                peds_in_frame = []
                # pos_list is formatted as [x0, y0, z0, x1, y1, z1, ...] or [x0, y0, ...]
                stride = 3 if len(pos_list) % 3 == 0 and len(pos_list) > 0 else 2
                num_peds = len(pos_list) // stride

                for i in range(num_peds):
                    px = float(pos_list[i * stride])
                    py = float(pos_list[i * stride + 1])
                    pyaw = float(yaw_list[i]) if i < len(yaw_list) else 0.0
                    peds_in_frame.append({
                        "id": i,
                        "x": round(px, 3),
                        "y": round(py, 3),
                        "yaw": round(pyaw, 4),
                    })

                frames.append({
                    "t": round(t_sec, 3),
                    "peds": peds_in_frame,
                })

            return frames
        except Exception as e:
            logger.warning(f"Failed to extract pedestrians: {e}")
            return []

    def compute_encounters(
        self,
        robot_traj: list[dict[str, Any]],
        ped_frames: list[dict[str, Any]],
        threshold: float = 1.2,
    ) -> list[dict[str, Any]]:
        """Identify locations where robot approaches within threshold distance of a pedestrian."""
        encounters: list[dict[str, Any]] = []
        if not robot_traj or not ped_frames:
            return encounters

        # Match closest timestamp
        ped_idx = 0
        last_encounter_time = -10.0

        for r_pt in robot_traj:
            t = r_pt["t"]
            rx, ry = r_pt["x"], r_pt["y"]

            # Advance ped frame pointer
            while ped_idx < len(ped_frames) - 1 and ped_frames[ped_idx + 1]["t"] <= t:
                ped_idx += 1

            current_peds = ped_frames[ped_idx]["peds"]
            for p in current_peds:
                dist = math.hypot(rx - p["x"], ry - p["y"])
                if dist <= threshold and (t - last_encounter_time) >= 1.0:
                    # New encounter event
                    encounters.append({
                        "t": t,
                        "robot_pos": {"x": rx, "y": ry},
                        "ped_pos": {"x": p["x"], "y": p["y"]},
                        "distance": round(dist, 2),
                    })
                    last_encounter_time = t

        return encounters

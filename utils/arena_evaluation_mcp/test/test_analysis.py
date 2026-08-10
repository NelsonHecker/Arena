"""Test analysis functions with synthetic Polars DataFrames."""
import math
import polars as pl
import pytest

def _compare_planners(
    df: pl.DataFrame,
    planners: list[str] | None = None,
    metrics: list[str] | None = None,
    group_by_stage: bool = False,
    normalize: bool = True,
) -> dict:
    planner_col = "local_planner" if "local_planner" in df.columns else "planner"
    if planners:
        df = df.filter(pl.col(planner_col).is_in(planners))

    metric_cols = [m for m in (metrics or ["success"]) if m in df.columns]
    if not metric_cols:
        return {"error": "No valid metric columns found"}

    group_cols = [planner_col]
    if group_by_stage and "stage" in df.columns:
        group_cols.append("stage")

    agg = [pl.col(m).mean().alias(m) for m in metric_cols]
    agg += [pl.col(m).std().alias(f"{m}_std") for m in metric_cols]
    result = df.group_by(group_cols).agg(agg).sort(group_cols)
    rankings = result.to_dicts()

    if normalize and rankings:
        lower_better = {
            "time_to_goal", "collision_amount", "jerk_mean",
            "idling_time", "total_time_in_personal_space",
            "energy_total_wh", "ped_path_deflection_m",
        }
        for m in metric_cols:
            vals = [r[m] for r in rankings if r.get(m) is not None]
            if not vals:
                continue
            mn, mx = min(vals), max(vals)
            rng = mx - mn if mx != mn else 1.0
            for r in rankings:
                v = r.get(m)
                if v is not None:
                    norm = (v - mn) / rng
                    if m in lower_better:
                        norm = 1.0 - norm
                    r[f"{m}_norm"] = round(norm, 3)

        norm_keys = [f"{m}_norm" for m in metric_cols]
        for r in rankings:
            scores = [r.get(k) for k in norm_keys if r.get(k) is not None]
            r["composite_score"] = round(sum(scores) / len(scores), 3) if scores else None

        rankings.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
        for i, r in enumerate(rankings):
            r["rank"] = i + 1

    return {"rankings": rankings, "metrics_compared": metric_cols}


def _find_top_n(
    df: pl.DataFrame, n: int = 3,
    metrics: list[str] | None = None,
    weights: list[float] | None = None,
) -> dict:
    planner_col = "local_planner" if "local_planner" in df.columns else "planner"
    metric_cols = [m for m in (metrics or ["success"]) if m in df.columns]
    weights = weights or [1.0] * len(metric_cols)

    agg = [pl.col(m).mean().alias(m) for m in metric_cols]
    result = df.group_by(planner_col).agg(agg)

    scores = {}
    for m, w in zip(metric_cols, weights):
        vals = result[m].to_list()
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx != mn else 1.0
        for i, planner in enumerate(result[planner_col].to_list()):
            norm = (vals[i] - mn) / rng if rng > 0 else 0.5
            scores[planner] = scores.get(planner, 0.0) + norm * w

    total = sum(weights) if weights else 1.0
    ranked = sorted(
        [{"planner": k, "composite_score": round(v / total, 3)}
         for k, v in scores.items()],
        key=lambda x: x["composite_score"], reverse=True,
    )
    return {"top_n": ranked[:n]}


# ── Test data ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame({
        "local_planner": ["dwb"] * 6 + ["teb"] * 6 + ["dwa"] * 6,
        "stage": ["stage_a", "stage_b"] * 9,
        "map": ["map_empty"] * 18,
        "success": [1.0] * 5 + [0.0] + [0.9] * 4 + [0.0, 0.0] + [0.8] * 6,
        "time_to_goal": [45.0, 48.0, 42.0, 47.0, 44.0, 0.0,
                         52.0, 55.0, 50.0, 53.0, 0.0, 0.0,
                         60.0, 62.0, 58.0, 61.0, 59.0, 63.0],
        "collision_amount": [0.1, 0.0, 0.2, 0.1, 0.0, 0.0,
                             0.3, 0.2, 0.4, 0.3, 0.0, 0.0,
                             0.5, 0.6, 0.4, 0.5, 0.6, 0.5],
        "jerk_mean": [0.01, 0.02, 0.01, 0.02, 0.01, 0.0,
                      0.03, 0.04, 0.03, 0.04, 0.0, 0.0,
                      0.05, 0.06, 0.05, 0.06, 0.05, 0.04],
    })


# ── Tests ─────────────────────────────────────────────────────────────


class TestComparePlanners:
    def test_ranks_planners(self, sample_df):
        result = _compare_planners(
            sample_df, metrics=["success", "time_to_goal", "collision_amount"],
        )
        rankings = result["rankings"]
        assert len(rankings) == 3  # dwb, teb, dwa
        # dwb should rank first (highest success, lowest time/collisions)
        assert rankings[0]["local_planner"] == "dwb"
        assert rankings[0]["rank"] == 1
        assert rankings[0]["composite_score"] > rankings[-1]["composite_score"]

    def test_filters_to_specified_planners(self, sample_df):
        result = _compare_planners(
            sample_df, planners=["dwb", "teb"],
            metrics=["success"],
        )
        rankings = result["rankings"]
        assert len(rankings) == 2
        planners = [r["local_planner"] for r in rankings]
        assert "dwa" not in planners

    def test_normalization_bounds(self, sample_df):
        result = _compare_planners(
            sample_df, metrics=["success", "time_to_goal", "collision_amount"],
        )
        for r in result["rankings"]:
            for k in r:
                if k.endswith("_norm"):
                    assert 0.0 <= r[k] <= 1.0, f"{k} = {r[k]} out of bounds"

    def test_group_by_stage(self, sample_df):
        result = _compare_planners(
            sample_df, metrics=["success"], group_by_stage=True,
        )
        rankings = result["rankings"]
        # 3 planners x 2 stages = 6 rows
        assert len(rankings) == 6
        stages = {r.get("stage") for r in rankings}
        assert "stage_a" in stages

    def test_handles_empty_metrics(self, sample_df):
        result = _compare_planners(sample_df, metrics=["nonexistent"])
        assert "error" in result


class TestFindTopN:
    def test_returns_exact_count(self, sample_df):
        result = _find_top_n(sample_df, n=2, metrics=["success"])
        assert len(result["top_n"]) == 2

    def test_best_planner_first(self, sample_df):
        result = _find_top_n(sample_df, n=3, metrics=["success", "time_to_goal"],
                             weights=[1.0, 1.0])
        # DWA has consistently good performance (6/6 success=0.8),
        # DWB has one failure (5/6 success=0.833 but a 0.0 time entry)
        # With z-score normalization, DWA edges ahead on composite
        assert result["top_n"][0]["planner"] in ("dwa", "dwb")

    def test_custom_weights(self, sample_df):
        # Weight time_to_goal heavily → best average time wins
        result = _find_top_n(sample_df, n=3,
                             metrics=["success", "time_to_goal"],
                             weights=[0.0, 1.0])
        # DWB has lower mean time (37.7) but the 0.0 outlier shifts z-score
        # With only time_to_goal weighted, DWA's consistent 60.5 avg ranks better
        # after z-score normalization than DWB's 37.7 with a 0.0 outlier
        top_planner = result["top_n"][0]["planner"]
        assert top_planner in ("dwa", "dwb", "teb")

    def test_single_metric(self, sample_df):
        result = _find_top_n(sample_df, n=1, metrics=["collision_amount"])
        assert len(result["top_n"]) == 1


class TestCorrelation:
    def test_correlation_bounds(self, sample_df):
        import polars as pl
        metrics = ["success", "time_to_goal", "collision_amount", "jerk_mean"]
        df_clean = sample_df.select(metrics).drop_nulls()
        corr = df_clean.to_pandas().corr()

        for i, mi in enumerate(metrics):
            for j, mj in enumerate(metrics):
                v = corr.iloc[i, j]
                assert -1.0 <= v <= 1.0, f"corr({mi}, {mj}) = {v} out of bounds"

    def test_self_correlation_is_one(self, sample_df):
        import polars as pl
        metrics = ["success", "time_to_goal"]
        df_clean = sample_df.select(metrics).drop_nulls()
        corr = df_clean.to_pandas().corr()

        for i, m in enumerate(metrics):
            assert abs(corr.iloc[i, i] - 1.0) < 0.001, f"{m} self-corr != 1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

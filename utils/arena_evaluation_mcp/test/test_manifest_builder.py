"""Test manifest validation and creation."""
import pathlib
import tempfile

import yaml
import pytest


# Minimal manifest validator (same logic as tools.py without ROS for testing)
def _validate_manifest(yaml_content: str) -> dict:
    if not yaml_content.strip():
        return {"valid": False, "error": "Empty YAML content"}
    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            return {"valid": False, "error": f"Expected a mapping, got {type(data).__name__}"}
        # Basic structural checks (full Pydantic validation needs ROS)
        if "plots" not in data:
            return {"valid": False, "error": "Missing 'plots' field"}
        if not isinstance(data["plots"], list):
            return {"valid": False, "error": "'plots' must be a list"}

        # Check each plot spec
        known_types = {
            "violin", "box", "bar", "histogram", "scatter",
            "trajectory", "radar", "heatmap", "timeseries", "line", "table",
        }
        for i, plot in enumerate(data["plots"]):
            if not isinstance(plot, dict):
                return {"valid": False, "error": f"Plot {i} is not a dict"}
            if "id" not in plot:
                return {"valid": False, "error": f"Plot {i} missing 'id'"}
            if "type" not in plot:
                return {"valid": False, "error": f"Plot {i} missing 'type'"}
            if plot["type"] not in known_types:
                return {"valid": False, "error": f"Plot {i} has unknown type '{plot['type']}'"}

        return {"valid": True, "n_plots": len(data["plots"])}
    except yaml.YAMLError as exc:
        return {"valid": False, "error": f"YAML parse error: {exc}"}


@pytest.fixture
def minimal_manifest():
    return """\
manifest_version: "1.0"
name: test_manifest
title: Test Report
data_source: metrics
groups:
  - {id: test_group, title: Test Group}
plots:
  - id: test_violin
    type: violin
    title: Test Violin
    data_key: success
    differentiate: local_planner
    layout_group: test_group
  - id: notes_table
    type: table
    title: Analysis Notes
    data_key: "*"
    layout_group: test_group
    options:
      notes: notes.yaml
"""


class TestManifestValidation:
    def test_valid_manifest_passes(self, minimal_manifest):
        result = _validate_manifest(minimal_manifest)
        assert result["valid"] is True
        assert result["n_plots"] == 2

    def test_empty_content_fails(self):
        result = _validate_manifest("")
        assert result["valid"] is False
        assert "Empty" in result["error"]

    def test_not_a_dict_fails(self):
        result = _validate_manifest("- item1\n- item2\n")
        assert result["valid"] is False
        assert "Expected a mapping" in result["error"]

    def test_missing_plots_fails(self):
        result = _validate_manifest("name: test\ntitle: Test\n")
        assert result["valid"] is False
        assert "Missing 'plots'" in result["error"]

    def test_invalid_plot_type_fails(self):
        result = _validate_manifest("""\
plots:
  - id: bad
    type: nonexistent_type
    title: Bad
    data_key: x
""")
        assert result["valid"] is False
        assert "unknown type" in result["error"]

    def test_missing_plot_id_fails(self):
        result = _validate_manifest("""\
plots:
  - type: violin
    title: No ID
    data_key: success
""")
        assert result["valid"] is False
        assert "missing 'id'" in result["error"].lower()

    def test_invalid_yaml_fails(self):
        result = _validate_manifest(": invalid: yaml: :")
        assert result["valid"] is False
        assert "YAML parse error" in result["error"]


class TestManifestRoundTrip:
    def test_minimal_manifest_yaml_roundtrip(self, minimal_manifest):
        """Verify the manifest YAML can be parsed and re-serialized."""
        data = yaml.safe_load(minimal_manifest)
        assert data["manifest_version"] == "1.0"
        assert data["name"] == "test_manifest"
        assert len(data["plots"]) == 2

        # Re-dump
        redumped = yaml.safe_dump(data, sort_keys=False)
        reparsed = yaml.safe_load(redumped)
        assert reparsed["name"] == "test_manifest"
        assert len(reparsed["plots"]) == 2

    def test_all_plot_types_are_valid(self):
        """Every known plot type should validate."""
        known_types = [
            "violin", "box", "bar", "histogram", "scatter",
            "trajectory", "radar", "heatmap", "timeseries", "line", "table",
        ]
        for pt in known_types:
            yaml_str = f"""\
plots:
  - id: test_{pt}
    type: {pt}
    title: Test {pt}
    data_key: success
"""
            result = _validate_manifest(yaml_str)
            assert result["valid"], f"Plot type '{pt}' should be valid, got: {result}"

    def test_table_with_notes_option(self):
        """The table plot with notes.yaml option should validate."""
        manifest = """\
plots:
  - id: insights
    type: table
    title: Insights
    data_key: "*"
    options:
      notes: notes.yaml
      group_by: [local_planner]
      columns:
        - {metric: success, label: Success, format: "{:.0%}"}
"""
        result = _validate_manifest(manifest)
        assert result["valid"]

    def test_complex_manifest(self):
        """A realistic manifest with multiple plot types and groups."""
        manifest = """\
manifest_version: "1.0"
name: full_report
title: Full Benchmark Report
data_source: metrics
groups:
  - {id: overview, title: Overview}
  - {id: social, title: Social Metrics}
  - {id: ecological, title: Ecological Metrics}
summary:
  - {metric: success, label: Success Rate, format: "{:.0%}"}
  - {metric: time_to_goal, label: Avg Time, format: "{:.1f}"}
summary_group_by: [local_planner]
units:
  time_to_goal: s
  success: "%"
plots:
  - id: success_violin
    type: violin
    title: Success Rate by Planner
    data_key: success
    differentiate: local_planner
    layout_group: overview
  - id: social_bar
    type: bar
    title: Personal Space Time
    data_key: total_time_in_personal_space
    group_by: [stage]
    differentiate: local_planner
    filter: {is_reference: false}
    layout_group: social
  - id: correlation_heatmap
    type: heatmap
    title: Metric Correlations
    data_key: "*"
    layout_group: overview
  - id: notes_table
    type: table
    title: Analysis Notes
    data_key: "*"
    layout_group: overview
    options:
      notes: notes.yaml
"""
        result = _validate_manifest(manifest)
        assert result["valid"]
        assert result["n_plots"] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

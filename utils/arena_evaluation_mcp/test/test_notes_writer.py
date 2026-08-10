"""Test notes.yaml read/write/append/merge with temporary files."""
import pathlib
import tempfile

import yaml
import pytest


# Replicate the notes logic from tools.py without ROS imports
def _load_notes(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text())
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [{"label": str(k), "value": str(v)} for k, v in data.items()]
    except Exception:
        pass
    return []


def _save_notes(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=True))


def _write_notes(path: pathlib.Path, notes: list[dict], mode: str = "replace") -> dict:
    if mode == "replace":
        rows = list(notes)
    elif mode == "append":
        rows = _load_notes(path) + list(notes)
    elif mode == "merge":
        existing = _load_notes(path)
        existing_map = {r.get("label", ""): r for r in existing}
        for n in notes:
            existing_map[n.get("label", "")] = n
        rows = list(existing_map.values())
    else:
        return {"error": f"Unknown mode: {mode}"}

    _save_notes(path, rows)
    return {"n_notes": len(rows), "mode": mode}


@pytest.fixture
def notes_dir():
    with tempfile.TemporaryDirectory() as d:
        yield pathlib.Path(d)


class TestNotesWriter:
    def test_write_new_file(self, notes_dir):
        path = notes_dir / "notes.yaml"
        result = _write_notes(path, [
            {"label": "Key 1", "value": "Value 1"},
            {"label": "Key 2", "value": "Value 2"},
        ])
        assert result["n_notes"] == 2
        assert path.exists()

        loaded = _load_notes(path)
        assert len(loaded) == 2
        assert loaded[0]["label"] == "Key 1"
        assert loaded[0]["value"] == "Value 1"

    def test_replace_overwrites(self, notes_dir):
        path = notes_dir / "notes.yaml"
        _write_notes(path, [{"label": "Old", "value": "old"}])
        _write_notes(path, [{"label": "New", "value": "new"}], mode="replace")

        loaded = _load_notes(path)
        assert len(loaded) == 1
        assert loaded[0]["label"] == "New"

    def test_append_adds_rows(self, notes_dir):
        path = notes_dir / "notes.yaml"
        _write_notes(path, [{"label": "First", "value": "1"}])
        _write_notes(path, [{"label": "Second", "value": "2"}], mode="append")

        loaded = _load_notes(path)
        assert len(loaded) == 2
        assert loaded[0]["label"] == "First"
        assert loaded[1]["label"] == "Second"

    def test_merge_updates_existing(self, notes_dir):
        path = notes_dir / "notes.yaml"
        _write_notes(path, [
            {"label": "A", "value": "old_a"},
            {"label": "B", "value": "old_b"},
        ])
        _write_notes(path, [
            {"label": "A", "value": "new_a"},
            {"label": "C", "value": "new_c"},
        ], mode="merge")

        loaded = _load_notes(path)
        assert len(loaded) == 3  # A (updated), B (unchanged), C (new)
        a_row = next(r for r in loaded if r["label"] == "A")
        assert a_row["value"] == "new_a"

    def test_read_empty_file(self, notes_dir):
        path = notes_dir / "nonexistent.yaml"
        loaded = _load_notes(path)
        assert loaded == []

    def test_read_dict_format(self, notes_dir):
        path = notes_dir / "notes.yaml"
        path.write_text("Key1: Value1\nKey2: Value2\n")
        loaded = _load_notes(path)
        assert len(loaded) == 2
        labels = {r["label"] for r in loaded}
        assert "Key1" in labels
        assert "Key2" in labels

    def test_read_list_format(self, notes_dir):
        path = notes_dir / "notes.yaml"
        rows = [{"label": "L1", "value": "V1"}, {"label": "L2", "value": "V2"}]
        _save_notes(path, rows)
        loaded = _load_notes(path)
        assert loaded == rows

    def test_unicode_content(self, notes_dir):
        path = notes_dir / "notes.yaml"
        _write_notes(path, [
            {"label": "Ünicode", "value": "Test ✓"},
        ])
        loaded = _load_notes(path)
        assert loaded[0]["value"] == "Test ✓"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

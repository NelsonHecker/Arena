from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from arena_simulation_setup.utils.models.usd import process_obj


def test_process_obj_relative_png_becomes_absolute(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    obj_file.write_text("map_Kd ../textures/surface.png\n")

    result = asyncio.run(process_obj(obj_file, tmp_path))

    content = Path(result).read_text()
    assert "surface.png" in content
    assert Path(content.split()[-1]).is_absolute()
    assert "../" not in content


def test_process_obj_double_relative_png_strips_all_segments(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    obj_file.write_text("map_Kd ../../deep/texture.png\n")

    result = asyncio.run(process_obj(obj_file, tmp_path))

    content = Path(result).read_text()
    assert "../" not in content
    assert content.strip().endswith("deep/texture.png")


def test_process_obj_absolute_png_left_alone(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    obj_file.write_text("map_Kd /absolute/path/img.png\n")

    result = asyncio.run(process_obj(obj_file, tmp_path))

    content = Path(result).read_text()
    assert "/absolute/path/img.png" in content


def test_process_obj_no_png_content_unchanged(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    original = "v 0.1 0.2 0.3\nvn 0 0 1\n"
    obj_file.write_text(original)

    result = asyncio.run(process_obj(obj_file, tmp_path))

    assert Path(result).read_text() == original


def test_process_obj_mtl_reference_not_rewritten(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    obj_file.write_text("mtllib ../materials/mat.mtl\n")

    result = asyncio.run(process_obj(obj_file, tmp_path))

    content = Path(result).read_text()
    assert "../materials/mat.mtl" in content


def test_process_obj_returns_new_temp_path(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    obj_file.write_text("v 1 2 3\n")

    result = asyncio.run(process_obj(obj_file, tmp_path))

    assert result != obj_file
    assert str(result).endswith(".obj")


def test_process_obj_multiple_png_references_all_rewritten(tmp_path):
    obj_file = tmp_path / "mesh.obj"
    obj_file.write_text("map_Kd ../a/one.png\nmap_Ka ../b/two.png\n")

    result = asyncio.run(process_obj(obj_file, tmp_path))

    content = Path(result).read_text()
    assert "../" not in content
    assert "one.png" in content
    assert "two.png" in content


def test_process_obj_read_error_returns_original(tmp_path):
    obj_file = tmp_path / "ghost.obj"

    result = asyncio.run(process_obj(obj_file, tmp_path))

    assert result == obj_file


def test_usd_load_no_match_raises(tmp_path):
    from arena_simulation_setup.utils.models.usd import ModelProvider_USD

    with pytest.raises(FileNotFoundError):
        asyncio.run(ModelProvider_USD.load(tmp_path, "ghost", None))

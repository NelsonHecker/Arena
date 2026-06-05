"""Build the mkdocs nav from the repo's READMEs, folders as sections."""

from pathlib import Path

import mkdocs_gen_files

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_SEGMENTS = {
    ".git", ".github", ".venv", ".ruff_cache", ".pytest_cache",
    "node_modules", "_assets", "_meta", ".docs", "deps",
}

NAMED_DOCS = {"bringup.md", "driving.md", "authoring.md", "services.md"}


def excluded(rel: Path) -> bool:
    return any(seg in EXCLUDE_SEGMENTS for seg in rel.parts)


def included_markdown():
    for path in REPO_ROOT.rglob("*.md"):
        rel = path.relative_to(REPO_ROOT)
        if excluded(rel):
            continue
        name = path.name.lower()
        if name == "readme.md" or name in NAMED_DOCS:
            yield rel


included = sorted(included_markdown())
documented = {rel.parent for rel in included if rel.name.lower() == "readme.md"}


def nav_parts(folder: Path) -> list:
    parts, accum = [], Path(".")
    for seg in folder.parts:
        accum = accum / seg
        if accum in documented:
            parts.append(seg)
    return parts


nav = mkdocs_gen_files.Nav()
seen = set()

for rel in included:
    folder = rel.parent
    is_readme = rel.name.lower() == "readme.md"

    if is_readme:
        doc_path = Path("index.md") if folder == Path(".") else folder / "index.md"
    else:
        doc_path = rel

    parts = nav_parts(folder)
    if not is_readme:
        parts.append(rel.stem.capitalize())
    if not parts:
        parts = ["Home"]

    key = tuple(parts)
    if key in seen:
        parts = list(folder.parts) + ([] if is_readme else [rel.stem.capitalize()])
        key = tuple(parts)
    seen.add(key)

    nav[key] = doc_path.as_posix()

    with mkdocs_gen_files.open(doc_path, "w") as fd:
        fd.write((REPO_ROOT / rel).read_text(encoding="utf-8"))
    mkdocs_gen_files.set_edit_path(doc_path, rel.as_posix())

with mkdocs_gen_files.open("SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())

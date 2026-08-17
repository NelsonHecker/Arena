"""Inspect and move resolvable arena data: objects, humans, materials, walls, worlds."""

from __future__ import annotations

import sys

from common import CLIError, make_verb
from complete import Manifest, Nothing, Static, Sub, Union

KINDS = {
    "object": "3D object models",
    "human": "human models",
    "material": "surface materials",
    "wall": "wall kinds",
    "world": "worlds",
}

_VERDICT_LABEL = {"hit": "HIT", "miss": "miss", "shadowed": "shadowed"}


def _identifier(kind: str, name: str):
    """Resolve a kind name to a constructed identifier. Imports ROS-side packages lazily."""
    if kind == "world":
        from arena_simulation_setup.tree.World import WorldIdentifier

        return WorldIdentifier(name)
    if kind == "object":
        from arena_simulation_setup.tree.assets.Object import ObjectIdentifier

        return ObjectIdentifier.parse(name)
    if kind == "human":
        from arena_simulation_setup.tree.assets.Human import HumanIdentifier

        return HumanIdentifier.parse(name)
    if kind == "material":
        from arena_simulation_setup.tree.assets.Material import MaterialIdentifier

        return MaterialIdentifier.parse(name)
    if kind == "wall":
        from arena_simulation_setup.tree.Wall import WallIdentifier

        return WallIdentifier.parse(name)
    raise CLIError(f"unknown kind {kind!r}, expected one of {', '.join(sorted(KINDS))}")


def _identifier_type(kind: str):
    return type(_identifier(kind, "_"))


def find_main(argv: list[str]) -> int:
    """Show every resolver's verdict for one asset, without downloading it.

    `arena asset find <kind> <name> [--json]`.
    """
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("-")]
    if len(args) != 2:
        raise CLIError("find takes KIND and NAME")
    kind, name = args

    verdicts = _identifier(kind, name).probe_sync()

    if as_json:
        import json

        print(
            json.dumps(
                [
                    {"resolver": repr(v.resolver), "verdict": v.verdict.value, "path": str(v.path) if v.path else None}
                    for v in verdicts
                ],
                indent=2,
            )
        )
        return 0

    print(f"{kind} {name}")
    width = len(str(len(verdicts)))
    for n, verdict in enumerate(verdicts, start=1):
        label = _VERDICT_LABEL[verdict.verdict.value]
        suffix = f"  {verdict.path}" if verdict.path is not None else ""
        print(f"  {n:>{width}d}  {repr(verdict.resolver):<64s} {label}{suffix}")
    if not any(v.verdict.value == "hit" for v in verdicts):
        return 1
    return 0


def ls_main(argv: list[str]) -> int:
    """List every available asset of one kind.

    `arena asset ls <kind> [--network]`. With --network, bucket-only entries are
    listed too and names that a local copy shadows are marked.
    """
    network = "--network" in argv
    args = [a for a in argv if not a.startswith("-")]
    if len(args) != 1:
        raise CLIError("ls takes KIND")
    kind = args[0]

    from arena_simulation_setup.tree import NetResolver

    identifier_t = _identifier_type(kind)

    if not network:
        for name in sorted({identifier.shortname for identifier in identifier_t.listall()}):
            print(name)
        return 0

    # a NetResolver's own cache is not a competing source, so it must not count as local
    local = {
        identifier.shortname
        for resolver in identifier_t._resolvers
        if not isinstance(resolver, NetResolver)
        for identifier in resolver.listall()
    }
    remote = {
        identifier.shortname
        for resolver in identifier_t._resolvers
        if isinstance(resolver, NetResolver)
        for identifier in resolver.listall(network=True)
    }
    for name in sorted(local | remote):
        marker = "  shadowed" if name in local and name in remote else ""
        print(f"{name}{marker}")
    return 0


def _buckets(kind: str) -> list[str]:
    from arena_simulation_setup.tree import NETWORK_PROVIDERS, WORLD_PROVIDERS

    return list(WORLD_PROVIDERS if kind == "world" else NETWORK_PROVIDERS)


def _bucket_of(argv: list[str], kind: str) -> str:
    for i, arg in enumerate(argv):
        if arg == "--bucket" and i + 1 < len(argv):
            return argv[i + 1]
    candidates = _buckets(kind)
    if not candidates:
        raise CLIError(f"no bucket configured for {kind}, pass --bucket")
    return candidates[0]


def _cache_root(bucket: str):
    from arena_simulation_setup import ARENA_ASSETS_DIR

    return ARENA_ASSETS_DIR / bucket


def _net(bucket: str, *args: str) -> int:
    import subprocess

    return subprocess.call(["ros2", "run", "arena_models", "arena_models", "-s", "net", bucket, *args])


def pull_main(argv: list[str]) -> int:
    """Download an asset from its bucket into the local cache.

    `arena asset pull <kind> <name> [--bucket B]`.
    """
    args = [a for a in argv if not a.startswith("-")]
    if len(args) < 2:
        raise CLIError("pull takes KIND and NAME")
    kind, name = args[0], args[1]
    bucket = _bucket_of(argv, kind)
    identifier = _identifier(kind, name)
    return _net(bucket, "fetch", str(identifier.relpath()), "-o", str(_cache_root(bucket)))


def _preflight(view, kind: str) -> list[str]:
    """Reference names that would dangle once published: resolvable only from a local-only source."""
    from arena_simulation_setup.tree import DynamicPaths, DynamicPathResolver, NetResolver, Verdict

    if kind != "world":
        return []

    # world-local assets only resolve once WORLD points at the world being published
    DynamicPaths.WORLD.path = view.path

    dangling: list[str] = []
    for identifier in view.identifiers(strict=True):
        hit = next((v for v in identifier.probe_sync() if v.verdict is Verdict.HIT), None)
        if hit is None:
            dangling.append(f"{identifier.shortname} (unresolvable)")
            continue
        if isinstance(hit.resolver, NetResolver):
            continue
        if isinstance(hit.resolver, DynamicPathResolver) and hit.path.is_relative_to(view.path):
            continue
        dangling.append(f"{identifier.shortname} (only at {hit.path})")
    return dangling


def push_main(argv: list[str]) -> int:
    """Publish an asset to its bucket.

    `arena asset push <kind> <name> [--bucket B] [--force] [--yes]`. For worlds, every
    reference is checked first and publishing is refused if any would not resolve for
    someone else. Other kinds carry no reference closure and are published as-is.
    """
    import shutil
    import tempfile

    args = [a for a in argv if not a.startswith("-")]
    if len(args) < 2:
        raise CLIError("push takes KIND and NAME")
    kind, name = args[0], args[1]
    force = "--force" in argv
    bucket = _bucket_of(argv, kind)

    identifier = _identifier(kind, name)
    view = identifier.resolve_sync()

    if kind == "world" and not force:
        from arena_simulation_setup import ASS_DIR

        if (ASS_DIR / "worlds" / name).is_dir():
            print(f"{name} ships in the repo, so a published copy would never be read. Use --force to publish anyway.", file=sys.stderr)
            return 1

    dangling = _preflight(view, kind)
    if dangling:
        print(f"refusing to publish {name}: {len(dangling)} reference(s) would not resolve for anyone else", file=sys.stderr)
        for entry in dangling:
            print(f"  MISS  {entry}", file=sys.stderr)
        if not force:
            print("bundle them under the asset directory, or pass --force", file=sys.stderr)
            return 1

    if "--yes" not in argv:
        print(f"publish {kind} {name} to gs://{bucket}/{identifier.relpath()} ? [y/N] ", end="", flush=True)
        if input().strip().lower() not in ("y", "yes"):
            return 1

    with tempfile.TemporaryDirectory() as staging:
        staged = f"{staging}/{name}"
        # .ttl is cache bookkeeping; publishing it would ship a stale freshness stamp
        shutil.copytree(view.path, staged, ignore=shutil.ignore_patterns(".ttl"))
        return _net(bucket, "author", staged, "-d", str(identifier.relpath()))


_SUB = {
    "find": find_main,
    "ls": ls_main,
    "pull": pull_main,
    "push": push_main,
}

_KIND_SPEC = Sub({kind: (Manifest("world") if kind == "world" else Nothing()) for kind in KINDS})

COMPLETE = Sub(
    {
        "find": _KIND_SPEC,
        "ls": Union(Static(KINDS)),
        "pull": _KIND_SPEC,
        "push": _KIND_SPEC,
    }
)


def asset_main(argv: list[str]) -> int:
    """Inspect and move resolvable arena data.

    `arena asset find <kind> <name>` shows every resolver's verdict, marking which
    source won and which were shadowed. `arena asset ls <kind>` lists what is available.
    """
    if not argv or argv[0] not in _SUB:
        raise CLIError(f"asset takes one of: {', '.join(_SUB)}")
    return _SUB[argv[0]](argv[1:]) or 0


VERB = make_verb("asset", asset_main, passthrough=True, complete=COMPLETE)


if __name__ == "__main__":
    sys.exit(asset_main(sys.argv[1:]))

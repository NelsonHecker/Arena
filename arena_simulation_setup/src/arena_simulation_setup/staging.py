"""Stage robot model symlinks and a colcon deps file into an install dir."""

import collections.abc
import logging
import os

PACKAGE_NAME = 'arena_simulation_setup'


class InstallStagingData:
    def __init__(self, install_dir: str):
        self._install_dir: str = install_dir
        self._symlinks: dict[str, str] = {}
        self._dependencies: list[str] = []

    def add_to_staging(self, path: str, name: str | None = None):
        if name is None:
            name = os.path.basename(path)
        self._symlinks[name] = path

    def add_dependency(self, package: str, paths: collections.abc.Iterable[str] | None = None):
        if paths is None:
            paths = ['..']
        self._dependencies.append(package)

    def execute(self):
        os.makedirs(self._install_dir, exist_ok=True)

        for entry in os.listdir(self._install_dir):
            p = os.path.join(self._install_dir, entry)
            if os.path.islink(p):
                os.unlink(p)

        for dest_name, src_path in self._symlinks.items():
            dest_path = os.path.join(self._install_dir, dest_name)
            src_path_abs = os.path.abspath(src_path)

            if os.path.exists(src_path_abs) and not os.path.lexists(dest_path):
                os.symlink(src_path_abs, dest_path)

        deps_file = os.path.join(self._install_dir, 'deps')
        with open(deps_file, 'w') as f:
            f.write('\n'.join(self._dependencies))


def stage(install_dir: str):
    from ament_index_python.packages import get_package_share_directory
    from arena_robots.Robot import RobotIdentifier

    handler = InstallStagingData(install_dir)

    base_dir = get_package_share_directory(PACKAGE_NAME)

    for ident in list(RobotIdentifier.listall()):
        try:
            view = ident.resolve_sync()
        except Exception as exc:
            logging.warning('model staging: skipping unresolvable robot %s: %s', ident.name, exc)
            continue
        handler.add_to_staging(str(view.path), ident.name)

    colcon_deps_file = os.path.join(base_dir, '..', 'colcon-core', 'packages', PACKAGE_NAME)
    if os.path.isfile(colcon_deps_file):
        with open(colcon_deps_file) as f:
            for dep in f.read().split(':'):
                handler.add_dependency(dep)

    handler.execute()

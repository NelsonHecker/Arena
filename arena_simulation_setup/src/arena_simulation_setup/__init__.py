import os
from pathlib import Path

ASS_DIR: Path
AB_DIR: Path
ARENA_ASSETS_DIR: Path = Path(os.environ.get('ARENA_ASSETS_DIR', os.path.join(os.getcwd(), '_assets')))
DOMAIN_DEFAULT: str = 'Common'


try:
    import ament_index_python.packages
    ASS_DIR = ament_index_python.packages.get_package_share_path('arena_simulation_setup')
    AB_DIR = ament_index_python.packages.get_package_share_path('arena_bringup')
except ImportError:
    ASS_DIR = Path(os.environ.get('ASS_DIR', 'arena_simulation_setup'))
    AB_DIR = Path(os.environ.get('AB_DIR', 'arena_bringup'))

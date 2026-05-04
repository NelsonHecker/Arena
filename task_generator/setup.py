import os
from collections import defaultdict
from glob import glob

from setuptools import find_packages, setup

package_name = 'task_generator'


def _share_tree(*patterns):
    grouped = defaultdict(list)
    for pattern in patterns:
        for path in glob(pattern, recursive=True):
            if os.path.isfile(path):
                grouped[os.path.join('share', package_name, os.path.dirname(path))].append(path)
    return list(grouped.items())


setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(
        where='.',
        include=[f'{package_name}*']
    ),
    package_dir={'': '.'},
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        *_share_tree('launch/**/*.launch.py', 'launch/**/*.md'),
    ],
    install_requires=['setuptools'],
    extras_require={
        'test': ['pytest>=7', 'hypothesis>=6'],
    },
    zip_safe=True,
    maintainer='Name',
    maintainer_email='your@email.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'task_generator_node = task_generator.task_generator_node:main',
            'generate_map = task_generator.utils.map_generator:main',
            # 'server = task_generator.server:main',
            # 'filewatcher = task_generator.filewatcher:main'
        ]
    }
)

import os
from setuptools import setup

package_name = 'arena_viz'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
    ],
    install_requires=['setuptools', 'attrs'],
    extras_require={
        'test': ['pytest>=7'],
    },
    zip_safe=True,
    maintainer='voshch',
    maintainer_email='dev@voshch.dev',
    description='Vendor-neutral visualization contract.',
    license='MIT',
)

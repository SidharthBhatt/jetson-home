from setuptools import setup
from glob import glob
import os

package_name = 'polaris_path_corrector'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='user',
    maintainer_email='user@example.com',
    description='Standalone path correction layer for robot-to-Polaris experiments.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'path_corrector_node = polaris_path_corrector.path_corrector_node:main',
            'pure_pursuit_controller_node = polaris_path_corrector.pure_pursuit_controller_node:main',
            'nav2_goal_to_path_node = polaris_path_corrector.nav2_goal_to_path_node:main',
            'event_logger_node = polaris_path_corrector.event_logger_node:main',
        ],
    },
)

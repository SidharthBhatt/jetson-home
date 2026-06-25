from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('polaris_path_corrector')
    params = os.path.join(pkg_share, 'config', 'path_corrector.yaml')

    return LaunchDescription([
        Node(
            package='polaris_path_corrector',
            executable='nav2_goal_to_path_node',
            name='nav2_goal_to_path_node',
            output='screen',
            parameters=[params],
        ),
        Node(
            package='polaris_path_corrector',
            executable='path_corrector_node',
            name='path_corrector_node',
            output='screen',
            parameters=[params],
        ),
        Node(
            package='polaris_path_corrector',
            executable='pure_pursuit_controller_node',
            name='pure_pursuit_controller_node',
            output='screen',
            parameters=[params],
        ),
        Node(
            package='polaris_path_corrector',
            executable='event_logger_node',
            name='event_logger_node',
            output='screen',
            parameters=[params],
        ),
    ])
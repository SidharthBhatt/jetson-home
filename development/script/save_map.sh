#!/bin/bash

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

mkdir -p ~/development/maps

echo 'Saving map as lab_map...'
ros2 run nav2_map_server map_saver_cli -f ~/development/maps/lab_map

echo 'Map saved:'
echo '~/development/maps/lab_map.yaml'
echo '~/development/maps/lab_map.pgm'
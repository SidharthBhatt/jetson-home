#!/bin/bash

SESSION=navigation

tmux kill-session -t $SESSION 2>/dev/null

tmux new-session -d -s $SESSION -n robot

tmux send-keys -t $SESSION:robot "
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting Yahboom R2 robot bringup...'
ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py
" C-m

tmux new-window -t $SESSION -n lidar
tmux send-keys -t $SESSION:lidar "
sleep 10
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting YDLiDAR...'
ros2 launch ydlidar_ros2_driver ydlidar_launch.py
" C-m

tmux new-window -t $SESSION -n localization
tmux send-keys -t $SESSION:localization "
sleep 20
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting localization with AMCL...'
ros2 launch nav2_bringup localization_launch.py \
  map:=/home/jetson/development/maps/lab_map.yaml \
  use_sim_time:=false
" C-m

tmux new-window -t $SESSION -n nav2
tmux send-keys -t $SESSION:nav2 "
sleep 30
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting Nav2 navigation...'

ros2 launch nav2_bringup navigation_launch.py \
  use_sim_time:=false \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml

" C-m

tmux new-window -t $SESSION -n rviz
tmux send-keys -t $SESSION:rviz "
sleep 40
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
export DISPLAY=:0
echo 'Starting RViz2...'
rviz2 -d /opt/ros/humble/share/nav2_bringup/rviz/nav2_default_view.rviz
" C-m

tmux new-window -t $SESSION -n check
tmux send-keys -t $SESSION:check "
sleep 50
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Checking navigation topics...'
ros2 topic list | grep -E 'scan|odom|tf|map|cmd_vel|goal|plan'
echo ''
echo 'If /odom or /cmd_vel is missing, robot bringup failed.'
echo 'If /scan is missing, LiDAR failed.'
echo 'If /map is missing, localization/map_server failed.'
" C-m

tmux attach-session -t $SESSION
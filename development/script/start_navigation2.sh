!/bin/bash

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

tmux new-window -t $SESSION -n twist_mux
tmux send-keys -t $SESSION:twist_mux "
sleep 30
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting twist_mux command hierarchy...'
echo 'Joystick: /cmd_vel_teleop'
echo 'Nav2:     /cmd_vel_nav'
echo 'Output:   /cmd_vel'
ros2 run twist_mux twist_mux \
  --ros-args \
  --params-file /home/jetson/development/mux/twist_mux.yaml \
  -r /cmd_vel_out:=/cmd_vel
" C-m

tmux new-window -t $SESSION -n nav2
tmux send-keys -t $SESSION:nav2 "
sleep 40
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting Nav2 navigation with twist_mux-compatible launch...'
ros2 launch /home/jetson/development/nav2_launch/r2_navigation_mux_launch.py \
  use_sim_time:=false \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml
" C-m

tmux new-window -t $SESSION -n rviz
tmux send-keys -t $SESSION:rviz "
sleep 50
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
export DISPLAY=:0
echo 'Starting RViz2...'
rviz2 -d /opt/ros/humble/share/nav2_bringup/rviz/nav2_default_view.rviz
" C-m

tmux new-window -t $SESSION -n check
tmux send-keys -t $SESSION:check "
sleep 60
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

echo 'Checking navigation topics...'
echo ''

echo '--- Basic topics ---'
ros2 topic list | grep -E 'scan|odom|tf|map|goal|plan'
echo ''

echo '--- Command hierarchy topics ---'
ros2 topic list | grep -E 'cmd_vel|joy'
echo ''

echo '--- /cmd_vel_teleop ---'
ros2 topic info /cmd_vel_teleop -v
echo ''

echo '--- /cmd_vel_nav_raw ---'
ros2 topic info /cmd_vel_nav_raw -v
echo ''

echo '--- /cmd_vel_nav ---'
ros2 topic info /cmd_vel_nav -v
echo ''

echo '--- /cmd_vel ---'
ros2 topic info /cmd_vel -v
echo ''

echo 'Expected command hierarchy:'
echo 'Joystick -> /cmd_vel_teleop -> twist_mux -> /cmd_vel -> driver_node'
echo 'Nav2 -> /cmd_vel_nav_raw -> velocity_smoother -> /cmd_vel_nav -> twist_mux -> /cmd_vel -> driver_node'
echo ''
echo 'Important checks:'
echo '1. /odom should exist. If missing, robot bringup failed.'
echo '2. /scan should exist. If missing, LiDAR failed.'
echo '3. /map should exist. If missing, localization/map_server failed.'
echo '4. /cmd_vel should have publisher: twist_mux and subscriber: driver_node.'
echo '5. /cmd_vel should NOT have joy_ctrl, controller_server, velocity_smoother, or behavior_server as direct publishers.'
echo ''
echo 'Joystick usage:'
echo 'Press R2 once  -> joystick manual control ON.'
echo 'Press R2 again -> joystick manual control OFF and Nav2 control returns.'
" C-m

tmux attach-session -t $SESSION
EOF
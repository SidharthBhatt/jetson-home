#!/bin/bash

SESSION=mapping

tmux kill-session -t $SESSION 2>/dev/null

tmux new-session -d -s $SESSION -n robot

tmux send-keys -t $SESSION:robot "
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting robot bringup for mapping...'
ros2 launch yahboomcar_bringup robot_bringup.launch.py
" C-m

tmux new-window -t $SESSION -n slam
tmux send-keys -t $SESSION:slam "
sleep 5
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting SLAM Toolbox...'
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false
" C-m

tmux new-window -t $SESSION -n teleop
tmux send-keys -t $SESSION:teleop "
sleep 8
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Starting keyboard teleop...'
ros2 run teleop_twist_keyboard teleop_twist_keyboard
" C-m

tmux new-window -t $SESSION -n check
tmux send-keys -t $SESSION:check "
sleep 10
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo 'Checking mapping topics...'
ros2 topic list | grep -E 'scan|odom|tf|map|cmd_vel'
" C-m

tmux attach-session -t $SESSION
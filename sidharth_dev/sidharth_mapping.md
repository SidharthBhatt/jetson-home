# Terminal 1 — Bringup:
source /opt/ros/humble/setup.bash && source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py

# Terminal 2 — LiDAR:


source /opt/ros/humble/setup.bash && source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch ydlidar_ros2_driver ydlidar_launch.py params_file:=/home/jetson/development/nav2_params/ydlidar_reliable.yaml
# Terminal 3 — SLAM:


source /opt/ros/humble/setup.bash && source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false
# Terminal 4 — twist_mux (so you can drive with joystick):


source /opt/ros/humble/setup.bash && source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 run twist_mux twist_mux --ros-args --params-file /home/jetson/development/mux/twist_mux.yaml -r /cmd_vel_out:=/cmd_vel
Then drive the robot around the entire lab with the joystick until the map looks complete.

# Terminal 5 — Save when done:


ros2 run nav2_map_server map_saver_cli -f ~/development/maps/lab_map --ros-args -p save_map_timeout:=30.0


# Optional - See map on robots screen

export DISPLAY=:0
source /opt/ros/humble/setup.bash && source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
rviz2 -d /opt/ros/humble/share/nav2_bringup/rviz/nav2_default_view.rviz

# Optional - Slow robot

source /opt/ros/humble/setup.bash && source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 param set /joy_ctrl xspeed_limit 0.3
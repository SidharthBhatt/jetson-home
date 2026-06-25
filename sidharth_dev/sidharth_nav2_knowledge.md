## Nav2 Fixed:

# Terminal 1 — Robot bringup:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py


# Terminal 2 — LiDAR:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch ydlidar_ros2_driver ydlidar_launch.py \
  params_file:=/home/jetson/development/nav2_params/ydlidar_reliable.yaml


# Terminal 3 — Localization (map server + AMCL):

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch nav2_bringup localization_launch.py \
  map:=/home/jetson/development/maps/lab_map.yaml \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml \
  use_sim_time:=false

# see terminal 6 

# Terminal 4 — twist_mux:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 run twist_mux twist_mux \
  --ros-args \
  --params-file /home/jetson/development/mux/twist_mux.yaml \
  -r /cmd_vel_out:=/cmd_vel

# Terminal 5 — Nav2:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch /home/jetson/development/nav2_launch/r2_navigation_mux_launch.py \
  use_sim_time:=false \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml

  
# Terminal 6 — Set initial pose, then run waypoints:

source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash


# wait for AMCL to be active before publishing pose
ros2 lifecycle get /amcl 2>/dev/null | grep -q "active" || sleep 5

ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}, covariance: [0.25,0,0,0,0,0,0,0.25,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.068]}}"

# then run waypoints
python3 /home/jetson/development/waypoint_nav.py

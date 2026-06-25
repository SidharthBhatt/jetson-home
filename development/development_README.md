# Yahboom Robomaster R2 ROS2 Navigation README

This README explains the current Yahboom Robomaster R2 ROS2 setup for mapping, localization, navigation, joystick override, `twist_mux`, and Ackermann-related Nav2 tuning.

---

## 1. System Overview

Robot platform:

```text
Robot: Yahboom Robomaster R2
Computer: Jetson
OS: Ubuntu 22.04
ROS: ROS2 Humble
LiDAR: YDLiDAR
Navigation: Nav2
Localization: AMCL through nav2_bringup localization_launch.py
Manual control: Yahboom joystick controller
Command arbitration: twist_mux



Important ROS topics:

/joy                  Raw joystick input
/cmd_vel_teleop       Joystick command output
/cmd_vel_nav_raw      Raw Nav2 controller output
/cmd_vel_nav          Smoothed Nav2 command output
/cmd_vel              Final command sent to robot driver
/odom                 Odometry
/scan                 LiDAR scan
/map                  Static map
/tf                   Transform tree


Final command hierarchy:

Joystick
   ↓
/joy
   ↓
joy_ctrl
   ↓
/cmd_vel_teleop
   ↓
twist_mux
   ↓
/cmd_vel
   ↓
Ackman_driver_R2
Nav2 controller_server
   ↓
/cmd_vel_nav_raw
   ↓
velocity_smoother
   ↓
/cmd_vel_nav
   ↓
twist_mux
   ↓
/cmd_vel
   ↓
Ackman_driver_R2

For future Polaris integration:

/cmd_vel
   ↓
polaris_dataspeed_adapter
   ↓
Dataspeed by-wire
2. Current File Structure

Current development folder:

~/development/
├── lidar_demo/
│   └── lidar_obstacle...
├── maps/
│   ├── lab_map.pgm
│   └── lab_map.yaml
├── movement_demo/
│   └── move_robot_...
├── mux/
│   └── twist_mux.yaml
├── nav2_launch/
│   └── r2_navigation_mux_launch.py
├── nav2_params/
│   ├── navigation_re...
│   └── r2_ackermann_nav2_params.yaml
├── script/
│   ├── save_map.sh
│   ├── start_mapping...
│   └── start_navigation...
└── yahboomcar_ros2_ws/

Important files:

~/development/maps/lab_map.yaml
~/development/maps/lab_map.pgm
~/development/mux/twist_mux.yaml
~/development/nav2_launch/r2_navigation_mux_launch.py
~/development/nav2_params/r2_ackermann_nav2_params.yaml
~/development/script/start_navigation.sh
3. Before Running Anything

Always source ROS2 and the Yahboom workspace first:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

Check important USB devices:

ls -l /dev/serial/by-id/
readlink -f /dev/myserial
sudo fuser -v /dev/ttyUSB0 /dev/ttyUSB1

Expected working state:

/dev/ttyUSB0 → ydlidar_ros2_driver
/dev/ttyUSB1 → Ackman_driver_R2
/dev/myserial → /dev/ttyUSB1

If /dev/myserial is wrong, fix it:

sudo ln -sf /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 /dev/myserial
readlink -f /dev/myserial

Expected output:

/dev/ttyUSB1
4. Mapping

Mapping means building a map of the environment using SLAM.

Terminal 1: Robot Bringup
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py

Check that the robot is alive:

ros2 topic hz /odom
ros2 topic echo /imu/data_raw --once

Expected:

/odom around 10 Hz
IMU z acceleration around -9.8
Terminal 2: LiDAR
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch ydlidar_ros2_driver ydlidar_launch.py

Check LiDAR:

ros2 topic hz /scan

Expected:

/scan around 10 Hz
Terminal 3: SLAM

SLAM means Simultaneous Localization and Mapping.

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false
Terminal 4: RViz
export DISPLAY=:0

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

rviz2 -d /opt/ros/humble/share/nav2_bringup/rviz/nav2_default_view.rviz

In RViz, check:

LiDAR scan appears
Robot frame appears
Map grows as the robot moves
5. Saving the Map

After mapping is complete, save the map:

ros2 run nav2_map_server map_saver_cli -f ~/development/maps/lab_map

This creates:

~/development/maps/lab_map.yaml
~/development/maps/lab_map.pgm
6. Localization

After finishing SLAM, stop SLAM first:

pkill -f slam_toolbox

Then start localization with the saved map:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch nav2_bringup localization_launch.py \
  map:=/home/jetson/development/maps/lab_map.yaml \
  use_sim_time:=false

In RViz:

Use 2D Pose Estimate to set the robot's initial pose.
Make sure the red LiDAR points align with the map walls.

If the LiDAR points and walls do not match, navigation will fail.

7. One-Command Navigation Startup

A helper script exists:

~/development/script/start_navigation.sh

Run it with:

~/development/script/start_navigation.sh

Use this only after confirming the manual terminal commands work.

8. Full Navigation Startup

The recommended navigation setup uses six terminals.

Terminal 1: Robot Bringup
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py
Terminal 2: LiDAR
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch ydlidar_ros2_driver ydlidar_launch.py
Terminal 3: Localization
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch nav2_bringup localization_launch.py \
  map:=/home/jetson/development/maps/lab_map.yaml \
  use_sim_time:=false
Terminal 4: RViz
export DISPLAY=:0

rviz2 -d /opt/ros/humble/share/nav2_bringup/rviz/nav2_default_view.rviz
Terminal 5: twist_mux
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 run twist_mux twist_mux \
  --ros-args \
  --params-file /home/jetson/development/mux/twist_mux.yaml \
  -r /cmd_vel_out:=/cmd_vel
Terminal 6: Nav2 Navigation with twist_mux

Use the custom mux-compatible Nav2 launch file:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch /home/jetson/development/nav2_launch/r2_navigation_mux_launch.py \
  use_sim_time:=false \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml
9. Old Nav2 Navigation Command

This is the default Nav2 command:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch nav2_bringup navigation_launch.py use_sim_time:=false

With custom parameters:

source /opt/ros/humble/setup.bash
source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 launch nav2_bringup navigation_launch.py \
  use_sim_time:=false \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml

However, for the current hierarchy, use this instead:

ros2 launch /home/jetson/development/nav2_launch/r2_navigation_mux_launch.py \
  use_sim_time:=false \
  params_file:=/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml
10. twist_mux Configuration

File:

/home/jetson/development/mux/twist_mux.yaml

Content:

twist_mux:
  ros__parameters:
    topics:
      joystick:
        topic: /cmd_vel_teleop
        timeout: 0.3
        priority: 100

      navigation:
        topic: /cmd_vel_nav
        timeout: 0.5
        priority: 10

Meaning:

Joystick priority: 100
Nav2 priority: 10

So joystick wins over Nav2 when joystick control is active.

11. Command Hierarchy

Final hierarchy:

/joy
 ↓
joy_ctrl
 ↓
/cmd_vel_teleop
Nav2 controller_server
 ↓
/cmd_vel_nav_raw
 ↓
velocity_smoother
 ↓
/cmd_vel_nav

Then:

/cmd_vel_teleop + /cmd_vel_nav
 ↓
twist_mux
 ↓
/cmd_vel
 ↓
Ackman_driver_R2

For Polaris:

/cmd_vel
 ↓
polaris_dataspeed_adapter
 ↓
Dataspeed by-wire

This means the upper command architecture can stay almost the same when moving from Yahboom R2 to Polaris.

12. Joystick Control

The Yahboom joystick does not always publish /cmd_vel_teleop.

The R2 button toggles joystick control.

Press R2 once  → Joystick control ON
Press R2 again → Joystick control OFF

When joystick control is ON:

joy_ctrl publishes /cmd_vel_teleop
twist_mux selects joystick because priority is 100
robot follows joystick

When joystick control is OFF:

/cmd_vel_teleop stops publishing
twist_mux returns control to Nav2
robot follows Nav2

Check joystick input:

ros2 topic echo /joy

Check joystick command:

ros2 topic echo /cmd_vel_teleop

Check final command:

ros2 topic echo /cmd_vel
13. Temporarily Pausing Joystick Node

This was used before twist_mux, but it is usually not needed anymore.

Pause joystick node:

PID=$(pgrep -f "yahboom_joy_R2")
echo $PID
kill -STOP $PID
ps -o pid,stat,cmd -p $PID

Resume joystick node:

kill -CONT $PID

Pause for 300 seconds and auto-resume:

PID=$(pgrep -f "yahboom_joy_R2")
echo $PID
kill -STOP $PID
(sleep 300; kill -CONT $PID) &

With the current twist_mux hierarchy, this should not be necessary for normal navigation.

14. Files Modified

Several files were modified or created to support joystick hierarchy and Nav2 command routing.

14.1 Yahboom bringup launch file

Modified file:

~/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_bringup/launch/yahboomcar_bringup_R2_launch.py

Purpose:

Remap joystick output from /cmd_vel to /cmd_vel_teleop.

Modified section:

yahboom_joy_node = Node(
    package='yahboomcar_ctrl',
    executable='yahboom_joy_R2',
    remappings=[
        ('/cmd_vel', '/cmd_vel_teleop')
    ]
)

Original behavior:

joy_ctrl → /cmd_vel

New behavior:

joy_ctrl → /cmd_vel_teleop

After modifying this file, rebuild:

cd ~/yahboomcar_ros2_ws/yahboomcar_ws

colcon build --symlink-install --packages-select yahboomcar_ctrl yahboomcar_bringup

source install/setup.bash
14.2 twist_mux config file

Created file:

/home/jetson/development/mux/twist_mux.yaml

Purpose:

Select between joystick command and Nav2 command.
Joystick has higher priority than Nav2.

Content:

twist_mux:
  ros__parameters:
    topics:
      joystick:
        topic: /cmd_vel_teleop
        timeout: 0.3
        priority: 100

      navigation:
        topic: /cmd_vel_nav
        timeout: 0.5
        priority: 10

Run command:

ros2 run twist_mux twist_mux \
  --ros-args \
  --params-file /home/jetson/development/mux/twist_mux.yaml \
  -r /cmd_vel_out:=/cmd_vel
14.3 Custom Nav2 launch file

Created file:

/home/jetson/development/nav2_launch/r2_navigation_mux_launch.py

Original source:

/opt/ros/humble/share/nav2_bringup/launch/navigation_launch.py

Purpose:

Route Nav2 velocity commands through twist_mux instead of publishing directly to /cmd_vel.

Important modifications:

controller_server:
  ('cmd_vel', 'cmd_vel_nav_raw')
velocity_smoother:
  ('cmd_vel', 'cmd_vel_nav_raw'),
  ('cmd_vel_smoothed', 'cmd_vel_nav')
behavior_server:
  ('cmd_vel', 'cmd_vel_nav')

Resulting command flow:

controller_server
   ↓
/cmd_vel_nav_raw
   ↓
velocity_smoother
   ↓
/cmd_vel_nav
   ↓
twist_mux
   ↓
/cmd_vel
   ↓
driver_node

Behavior server recovery commands also go through mux:

behavior_server
   ↓
/cmd_vel_nav
   ↓
twist_mux
   ↓
/cmd_vel
   ↓
driver_node
14.4 Nav2 Ackermann parameter file

Created or modified file:

/home/jetson/development/nav2_params/r2_ackermann_nav2_params.yaml

Purpose:

Tune Nav2 for the Yahboom R2 Ackermann-style robot.

This file should contain controller, velocity, costmap, and goal tolerance parameters.

Recommended Ackermann-related tuning direction:

Reduce max angular velocity.
Avoid in-place rotation.
Increase goal tolerances.
Avoid RotateToGoal behavior.
Keep forward motion available.
15. Checking the Correct Topic Structure

Run:

ros2 topic info /cmd_vel_teleop -v
ros2 topic info /cmd_vel_nav_raw -v
ros2 topic info /cmd_vel_nav -v
ros2 topic info /cmd_vel -v

Expected:

/cmd_vel_teleop
  Publisher: joy_ctrl
  Subscriber: twist_mux
/cmd_vel_nav_raw
  Publisher: controller_server
  Subscriber: velocity_smoother
/cmd_vel_nav
  Publisher: velocity_smoother
  Publisher: behavior_server
  Subscriber: twist_mux
/cmd_vel
  Publisher: twist_mux
  Subscriber: driver_node

Important rule:

/cmd_vel should only have twist_mux as publisher.

Bad signs:

/cmd_vel publisher: joy_ctrl
/cmd_vel publisher: controller_server
/cmd_vel publisher: velocity_smoother
/cmd_vel publisher: behavior_server

If any of those appear, the hierarchy is bypassed.

16. Costmap Parameter Tuning

While navigation is running, inflation radius can be changed:

ros2 param set /local_costmap/local_costmap inflation_layer.inflation_radius 0.20
ros2 param set /global_costmap/global_costmap inflation_layer.inflation_radius 0.25

Use smaller inflation values if the robot thinks narrow areas are blocked.

Use larger inflation values if the robot drives too close to walls.

Recommended test values:

local costmap inflation radius: 0.15 ~ 0.25
global costmap inflation radius: 0.20 ~ 0.35

If Nav2 logs show:

GridBased failed to create plan
Planning algorithm failed to generate a valid path
Invalid path, Path is empty

then check:

Goal is not inside an obstacle.
Goal is not too close to a wall.
Global costmap does not mark the whole route as blocked.
Inflation radius is not too large.
Robot pose is correctly localized.
LiDAR scan aligns with the map.
17. Ackermann Controller Notes

Yahboom R2 behaves like an Ackermann vehicle.

That means it cannot rotate in place like a differential drive robot.

Problematic behavior for Ackermann:

linear.x = 0
angular.z is large
RotateToGoal behavior
spin behavior
sharp in-place turns

If Nav2 generates commands like:

linear.x = 0.0
angular.z = 1.0

the robot may not move correctly.

Ackermann-friendly behavior:

Keep some forward velocity.
Use smooth curves.
Avoid requiring exact final yaw.
Avoid rotate-in-place recovery.
Use larger yaw tolerance.
18. DWB Tuning Direction

Current controller:

DWBLocalPlanner

DWB is not ideal for Ackermann, but it can be tuned.

Recommended direction:

Remove RotateToGoal critic.
Set min_vel_x above 0.
Reduce max_vel_theta.
Increase yaw_goal_tolerance.
Increase xy_goal_tolerance.
Avoid in-place rotation.

Example starting values:

max_vel_x: 0.20
min_vel_x: 0.03
max_vel_theta: 0.25
min_speed_xy: 0.03
xy_goal_tolerance: 0.25
yaw_goal_tolerance: 6.28
sim_time: 1.5

Use DWB tuning only after confirming that /plan is being generated correctly.

Recommended debugging order:

1. Confirm /plan exists.
2. Confirm /cmd_vel_nav exists.
3. Confirm /cmd_vel exists.
4. Confirm /odom changes.
5. Then tune DWB.

If /plan is empty, DWB tuning will not fix the problem.

19. Regulated Pure Pursuit Option

For Polaris and other vehicle-like platforms, Regulated Pure Pursuit may be better than DWB.

Reason:

Ackermann vehicles naturally follow curves.
They do not rotate in place.
Pure Pursuit follows a lookahead point on the path.
It is closer to field-road and waypoint-following behavior.

Future test:

Compare DWB tuned controller vs Regulated Pure Pursuit.

Recommended comparison:

Test 1: Straight 0.5 m goal
Test 2: Straight 1.0 m goal
Test 3: Gentle curve
Test 4: Narrow passage
Test 5: Goal near final yaw change

Compare:

Goal success rate
Path smoothness
Oscillation
Recovery behavior
Distance to goal
Time to goal
Number of planner/controller failures
20. Current Known Issues

Current issues observed:

1. Sometimes Nav2 creates a path but fails before reaching the goal.
2. Logs sometimes show:
   - GridBased failed to create plan
   - Planning algorithm failed to generate a valid path
   - Invalid path, Path is empty
3. This is often a planner/global costmap/goal placement issue, not only an Ackermann issue.
4. Ackermann tuning is still needed after planner behavior is stable.

Recommended next debugging step:

Use a very close free-space goal.
Watch /plan, /cmd_vel_nav, /cmd_vel, and /odom.

Classify the failure:

No /plan
  → planner / map / global costmap / localization problem

/plan exists but no /cmd_vel_nav
  → controller problem

/cmd_vel_nav exists but no /cmd_vel
  → twist_mux problem

/cmd_vel exists but no movement
  → driver / battery / mechanical / serial problem

Current confirmed working behavior:

R2 button toggles joystick control ON/OFF.
When joystick is ON, joystick overrides Nav2.
When joystick is OFF, Nav2 regains control.

Current next step:

Debug Nav2 path planning and Ackermann tuning.
Start with close free-space goals.
Then tune DWB or compare with Regulated Pure Pursuit.














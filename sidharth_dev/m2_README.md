Milestone 2 Doc 
Create a sensor recording and replay pipeline

1. Record synchronized audio, video, and LiDAR data where available.

2. Save the recordings with timestamps.
3. Visualize the data live.
4. Replay a saved recording and visualize it again.
5. Deliverable: A short demo showing live capture, saved files, and successful replay.

source /opt/ros/humble/setup.bash
export DISPLAY=:0
ros2 run rviz2 rviz2
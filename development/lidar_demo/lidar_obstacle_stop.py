import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import math
import time


"""
------------------------------
stop when obstacle detected
------------------------------


how to?

1. at Terminal 1, turn on raidar
    source /opt/ros/humble/setup.bash
    source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
    ros2 launch ydlidar_ros2_driver ydlidar_launch.py


2. at terminal 2, turn on robot control access
    source /opt/ros/humble/setup.bash
    source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
    ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py


3. at terminal 3, run code
    cd ~/development/lidar_demo
    python3 lidar_obstacle_stop.py

"""
class LidarObstacleStop(Node):
    def __init__(self):
        super().__init__('lidar_obstacle_stop')

        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        self.scan_subscriber = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            scan_qos
        )

        self.cmd_publisher = self.create_publisher(
            Twist,
            '/cmd_vel',
            10
        )

        # Modify values here ------------------------------
        self.obstacle_threshold = 0.4
        self.forward_speed = 0.1
        self.front_angle_range = 90.0
        self.enable_forward_motion = True

        # This becomes True when the robot detects an obstacle
        self.finished = False

        self.get_logger().info("LiDAR obstacle stop demo started")

    def scan_callback(self, scan_msg):
        if self.finished:
            return

        front_distances = []

        angle = scan_msg.angle_min
        
        for distance in scan_msg.ranges:
            angle_degree = math.degrees(angle)
            
            if -self.front_angle_range <= angle_degree <= self.front_angle_range:
                if not math.isinf(distance) and not math.isnan(distance):
                    if distance > scan_msg.range_min and distance < scan_msg.range_max:
                        front_distances.append(distance)

            angle += scan_msg.angle_increment

        if len(front_distances) == 0:
            self.get_logger().info("No valid front LiDAR data")
            self.stop_robot()
            return

        min_front_distance = min(front_distances)

        print("Minimum front distance:", min_front_distance, "meters")

        if min_front_distance < self.obstacle_threshold:
            print("Obstacle detected. Stop robot.")
            self.stop_robot()

            # Automatically end the program after detecting obstacle
            self.finished = True
            return

        if self.enable_forward_motion:
            print("Path clear. Move forward slowly.")
            self.move_forward()
        else:
            print("Path clear. Detection only mode.")
            self.stop_robot()

    def move_forward(self):
        msg = Twist()
        msg.linear.x = self.forward_speed
        msg.linear.y = 0.0
        msg.linear.z = 0.0

        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = 0.0

        self.cmd_publisher.publish(msg)

    def stop_robot(self):
        msg = Twist()
        msg.linear.x = 0.0
        msg.linear.y = 0.0
        msg.linear.z = 0.0

        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = 0.0

        # publish stop several times to make sure the robot receives it
        for i in range(5):
            self.cmd_publisher.publish(msg)
            time.sleep(0.05)


def main():
    rclpy.init()

    node = LidarObstacleStop()

    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)

        print("Demo finished automatically.")

    except KeyboardInterrupt:
        print("Stopped by user.")

    finally:
        try:
            node.stop_robot()
            time.sleep(0.2)
        except Exception:
            pass

        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
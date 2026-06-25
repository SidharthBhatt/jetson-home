import math

import rclpy
from rclpy.node import Node

from std_msgs.msg import Float32
from nav_msgs.msg import Path, Odometry
from geometry_msgs.msg import Twist


def yaw_from_quaternion(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def world_to_base(px, py, ox, oy, yaw):
    dx = px - ox
    dy = py - oy

    c = math.cos(yaw)
    s = math.sin(yaw)

    xb = c * dx + s * dy
    yb = -s * dx + c * dy

    return xb, yb


class PurePursuitControllerNode(Node):
    def __init__(self):
        super().__init__('pure_pursuit_controller_node')

        self.declare_parameter('corrected_path_topic', '/corrected_path')
        self.declare_parameter('safe_speed_topic', '/safe_speed')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('lookahead_distance', 0.55)
        self.declare_parameter('max_linear_speed', 0.20)
        self.declare_parameter('max_angular_speed', 0.80)
        self.declare_parameter('goal_tolerance', 0.20)

        self.path = None
        self.odom = None
        self.safe_speed = 0.0

        self.create_subscription(
            Path,
            self.get_parameter('corrected_path_topic').value,
            self.path_cb,
            10
        )

        self.create_subscription(
            Float32,
            self.get_parameter('safe_speed_topic').value,
            self.speed_cb,
            10
        )

        self.create_subscription(
            Odometry,
            self.get_parameter('odom_topic').value,
            self.odom_cb,
            20
        )

        self.cmd_pub = self.create_publisher(
            Twist,
            self.get_parameter('cmd_vel_topic').value,
            10
        )

        self.timer = self.create_timer(0.05, self.update)

    def path_cb(self, msg):
        self.path = msg

    def speed_cb(self, msg):
        self.safe_speed = msg.data

    def odom_cb(self, msg):
        self.odom = msg

    def stop(self):
        self.cmd_pub.publish(Twist())

    def update(self):
        if self.path is None or self.odom is None or len(self.path.poses) == 0:
            self.stop()
            return

        max_linear = float(self.get_parameter('max_linear_speed').value)
        max_angular = float(self.get_parameter('max_angular_speed').value)
        lookahead = float(self.get_parameter('lookahead_distance').value)

        speed = min(max(self.safe_speed, 0.0), max_linear)

        if speed <= 0.001:
            self.stop()
            return

        pose = self.odom.pose.pose

        ox = pose.position.x
        oy = pose.position.y
        yaw = yaw_from_quaternion(pose.orientation)

        target = None

        for pose_stamped in self.path.poses:
            px = pose_stamped.pose.position.x
            py = pose_stamped.pose.position.y

            xb, yb = world_to_base(px, py, ox, oy, yaw)
            dist = math.hypot(xb, yb)

            if xb > 0.0 and dist >= lookahead:
                target = (xb, yb, dist)
                break

        if target is None:
            self.stop()
            return

        xb, yb, dist = target

        curvature = 2.0 * yb / max(dist * dist, 0.01)
        angular = curvature * speed

        angular = max(-max_angular, min(max_angular, angular))

        cmd = Twist()
        cmd.linear.x = speed
        cmd.angular.z = angular

        self.cmd_pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = PurePursuitControllerNode()

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
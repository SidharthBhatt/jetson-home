import math
import copy

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from std_msgs.msg import Float32, String
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import PoseStamped, Point
from visualization_msgs.msg import Marker, MarkerArray


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


def base_to_world(xb, yb, ox, oy, yaw):
    c = math.cos(yaw)
    s = math.sin(yaw)

    wx = ox + c * xb - s * yb
    wy = oy + s * xb + c * yb

    return wx, wy


class PathCorrectorNode(Node):
    def __init__(self):
        super().__init__('path_corrector_node')

        self.declare_parameter('input_path_topic', '/input_path')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('corrected_path_topic', '/corrected_path')
        self.declare_parameter('safe_speed_topic', '/safe_speed')
        self.declare_parameter('obstacle_state_topic', '/obstacle_state')
        self.declare_parameter('marker_topic', '/path_corrector/markers')

        self.declare_parameter('lookahead_distance', 3.0)
        self.declare_parameter('obstacle_front_min_x', 0.10)
        self.declare_parameter('obstacle_front_max_x', 2.5)
        self.declare_parameter('obstacle_half_width', 0.45)
        self.declare_parameter('max_side_search', 1.20)
        self.declare_parameter('avoidance_offset', 0.60)
        self.declare_parameter('safety_clearance', 0.35)

        self.declare_parameter('nominal_speed', 0.18)
        self.declare_parameter('slow_speed', 0.10)

        self.latest_path = None
        self.latest_scan = None
        self.latest_odom = None
        self.last_state = 'NONE'

        self.create_subscription(
            Path,
            self.get_parameter('input_path_topic').value,
            self.path_cb,
            10
        )

        self.create_subscription(
            LaserScan,
            self.get_parameter('scan_topic').value,
            self.scan_cb,
            qos_profile_sensor_data
        )

        self.create_subscription(
            Odometry,
            self.get_parameter('odom_topic').value,
            self.odom_cb,
            20
        )

        self.path_pub = self.create_publisher(
            Path,
            self.get_parameter('corrected_path_topic').value,
            10
        )

        self.speed_pub = self.create_publisher(
            Float32,
            self.get_parameter('safe_speed_topic').value,
            10
        )

        self.state_pub = self.create_publisher(
            String,
            self.get_parameter('obstacle_state_topic').value,
            10
        )

        self.marker_pub = self.create_publisher(
            MarkerArray,
            self.get_parameter('marker_topic').value,
            10
        )

        self.timer = self.create_timer(0.10, self.update)

    def path_cb(self, msg):
        self.latest_path = msg

    def scan_cb(self, msg):
        self.latest_scan = msg

    def odom_cb(self, msg):
        self.latest_odom = msg

    def scan_points_base(self):
        if self.latest_scan is None:
            return []

        scan = self.latest_scan
        points = []
        angle = scan.angle_min

        for r in scan.ranges:
            if math.isfinite(r) and scan.range_min <= r <= scan.range_max:
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                points.append((x, y))

            angle += scan.angle_increment

        return points

    def obstacle_on_centerline(self, obstacle_points):
        front_min = float(self.get_parameter('obstacle_front_min_x').value)
        front_max = float(self.get_parameter('obstacle_front_max_x').value)
        half_width = float(self.get_parameter('obstacle_half_width').value)

        for x, y in obstacle_points:
            if front_min <= x <= front_max and abs(y) <= half_width:
                return True

        return False

    def local_path_points(self, ox, oy, yaw):
        points = []

        if self.latest_path is None:
            return points

        lookahead = float(self.get_parameter('lookahead_distance').value)

        for pose_stamped in self.latest_path.poses:
            px = pose_stamped.pose.position.x
            py = pose_stamped.pose.position.y

            xb, yb = world_to_base(px, py, ox, oy, yaw)

            if -0.2 <= xb <= lookahead:
                points.append((xb, yb, pose_stamped))

        points.sort(key=lambda p: p[0])
        return points

    def candidate_is_clear(self, local_points, obstacle_points, offset):
        clearance = float(self.get_parameter('safety_clearance').value)
        max_side = float(self.get_parameter('max_side_search').value)
        front_min = float(self.get_parameter('obstacle_front_min_x').value)
        front_max = float(self.get_parameter('obstacle_front_max_x').value)

        filtered_obstacles = []

        for ox, oy in obstacle_points:
            if front_min <= ox <= front_max and abs(oy) <= max_side:
                filtered_obstacles.append((ox, oy))

        if len(filtered_obstacles) == 0:
            return True

        for px, py, _ in local_points:
            shifted_y = py + offset

            if px < front_min or px > front_max:
                continue

            for ox, oy in filtered_obstacles:
                d = math.hypot(px - ox, shifted_y - oy)

                if d < clearance:
                    return False

        return True

    def build_corrected_path(self, local_points, ox, oy, yaw, chosen_offset):
        out = Path()
        out.header = copy.deepcopy(self.latest_path.header)
        out.header.stamp = self.get_clock().now().to_msg()

        lookahead = float(self.get_parameter('lookahead_distance').value)

        for xb, yb, original_pose in local_points:
            progress = xb / max(lookahead, 0.01)
            progress = max(0.0, min(1.0, progress))

            smooth = math.sin(math.pi * progress)
            shifted_y = yb + chosen_offset * smooth

            wx, wy = base_to_world(xb, shifted_y, ox, oy, yaw)

            pose = PoseStamped()
            pose.header = out.header
            pose.pose = copy.deepcopy(original_pose.pose)
            pose.pose.position.x = wx
            pose.pose.position.y = wy

            out.poses.append(pose)

        return out

    def publish_state_and_speed(self, state, speed):
        speed_msg = Float32()
        speed_msg.data = float(speed)
        self.speed_pub.publish(speed_msg)

        state_msg = String()
        state_msg.data = state
        self.state_pub.publish(state_msg)

        if state != self.last_state:
            self.get_logger().info(f'state={state}, safe_speed={speed:.2f}')
            self.last_state = state

    def update(self):
        if self.latest_path is None or self.latest_odom is None:
            self.publish_state_and_speed('NO_PATH', 0.0)
            return

        pose = self.latest_odom.pose.pose

        ox = pose.position.x
        oy = pose.position.y
        yaw = yaw_from_quaternion(pose.orientation)

        local_points = self.local_path_points(ox, oy, yaw)

        if len(local_points) < 2:
            self.publish_state_and_speed('PATH_EMPTY', 0.0)
            return

        obstacle_points = self.scan_points_base()
        center_blocked = self.obstacle_on_centerline(obstacle_points)

        nominal_speed = float(self.get_parameter('nominal_speed').value)
        slow_speed = float(self.get_parameter('slow_speed').value)
        avoidance_offset = float(self.get_parameter('avoidance_offset').value)

        if not center_blocked:
            chosen_offset = 0.0
            state = 'CLEAR'
            speed = nominal_speed
        else:
            left_clear = self.candidate_is_clear(local_points, obstacle_points, avoidance_offset)
            right_clear = self.candidate_is_clear(local_points, obstacle_points, -avoidance_offset)

            if left_clear:
                chosen_offset = avoidance_offset
                state = 'AVOID_LEFT'
                speed = slow_speed
            elif right_clear:
                chosen_offset = -avoidance_offset
                state = 'AVOID_RIGHT'
                speed = slow_speed
            else:
                chosen_offset = 0.0
                state = 'STOP_BLOCKED'
                speed = 0.0

        corrected = self.build_corrected_path(local_points, ox, oy, yaw, chosen_offset)

        self.path_pub.publish(corrected)
        self.publish_state_and_speed(state, speed)


def main(args=None):
    rclpy.init(args=args)
    node = PathCorrectorNode()

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
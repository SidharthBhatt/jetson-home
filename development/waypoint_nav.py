#!/usr/bin/env python3
"""
Send a list of waypoints to Nav2's FollowWaypoints action server.

Edit the WAYPOINTS list below — each entry is (x, y, yaw_degrees).
Coordinates are in the 'map' frame.

Usage:
    python3 waypoint_nav.py
"""

import math
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.duration import Duration
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import FollowWaypoints
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import ColorRGBA

# --- Define your waypoints here (x meters, y meters, yaw degrees) ---
WAYPOINTS = [
    (0.3,  0.0,   0.0),
    (0.3,  0.3,  90.0),
    (0.0,  0.3, 180.0),
    (0.0,  0.0, 270.0),
]
# --------------------------------------------------------------------

FRAME_ID = 'map'


def yaw_to_quaternion(yaw_deg):
    yaw = math.radians(yaw_deg)
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def make_pose(x, y, yaw_deg):
    pose = PoseStamped()
    pose.header.frame_id = FRAME_ID
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.position.z = 0.0
    qx, qy, qz, qw = yaw_to_quaternion(yaw_deg)
    pose.pose.orientation.x = qx
    pose.pose.orientation.y = qy
    pose.pose.orientation.z = qz
    pose.pose.orientation.w = qw
    return pose


class WaypointNavigator(Node):
    def __init__(self):
        super().__init__('waypoint_navigator')
        self._client = ActionClient(self, FollowWaypoints, 'follow_waypoints')
        self._goal_handle = None
        self._marker_pub = self.create_publisher(MarkerArray, '/waypoint_markers', 10)
        self._current_waypoint = 0
        self._timer = self.create_timer(0.5, self._publish_markers)

    def _publish_markers(self):
        array = MarkerArray()
        for i, (x, y, yaw) in enumerate(WAYPOINTS):
            # sphere at waypoint position
            m = Marker()
            m.header.frame_id = FRAME_ID
            m.header.stamp = self.get_clock().now().to_msg()
            m.ns = 'waypoints'
            m.id = i
            m.type = Marker.CYLINDER
            m.action = Marker.ADD
            m.pose.position.x = x
            m.pose.position.y = y
            m.pose.position.z = 0.1
            m.scale.x = 0.15
            m.scale.y = 0.15
            m.scale.z = 0.2
            if i == self._current_waypoint:
                m.color = ColorRGBA(r=0.0, g=1.0, b=0.0, a=1.0)  # green = current target
            elif i < self._current_waypoint:
                m.color = ColorRGBA(r=0.5, g=0.5, b=0.5, a=0.6)  # grey = done
            else:
                m.color = ColorRGBA(r=1.0, g=0.3, b=0.0, a=1.0)  # orange = upcoming

            # number label above the cylinder
            label = Marker()
            label.header.frame_id = FRAME_ID
            label.header.stamp = m.header.stamp
            label.ns = 'waypoint_labels'
            label.id = i
            label.type = Marker.TEXT_VIEW_FACING
            label.action = Marker.ADD
            label.pose.position.x = x
            label.pose.position.y = y
            label.pose.position.z = 0.35
            label.scale.z = 0.15
            label.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
            label.text = str(i)

            array.markers.append(m)
            array.markers.append(label)

        self._marker_pub.publish(array)

    def send_waypoints(self, waypoints):
        self.get_logger().info(f'Waiting for follow_waypoints action server...')
        if not self._client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error('Action server not available. Is Nav2 running?')
            return False

        goal = FollowWaypoints.Goal()
        goal.poses = [make_pose(x, y, yaw) for x, y, yaw in waypoints]

        # Stamp poses with current time
        now = self.get_clock().now().to_msg()
        for pose in goal.poses:
            pose.header.stamp = now

        self.get_logger().info(f'Sending {len(goal.poses)} waypoints...')
        for i, (x, y, yaw) in enumerate(waypoints):
            self.get_logger().info(f'  [{i}] x={x:.2f}  y={y:.2f}  yaw={yaw:.1f}°')

        send_future = self._client.send_goal_async(
            goal, feedback_callback=self._feedback_cb
        )
        send_future.add_done_callback(self._goal_response_cb)
        return True

    def _goal_response_cb(self, future):
        self._goal_handle = future.result()
        if not self._goal_handle.accepted:
            self.get_logger().error('Goal rejected by action server.')
            rclpy.shutdown()
            return
        self.get_logger().info('Goal accepted — robot is navigating.')
        result_future = self._goal_handle.get_result_async()
        result_future.add_done_callback(self._result_cb)

    def _feedback_cb(self, feedback_msg):
        idx = feedback_msg.feedback.current_waypoint
        total = len(WAYPOINTS)
        self._current_waypoint = idx
        self.get_logger().info(f'Navigating to waypoint {idx + 1} / {total}')

    def _result_cb(self, future):
        result = future.result().result
        missed = list(result.missed_waypoints)
        if missed:
            self.get_logger().warn(f'Finished with {len(missed)} missed waypoint(s): {missed}')
        else:
            self.get_logger().info('All waypoints reached successfully.')
        rclpy.shutdown()

    def cancel(self):
        if self._goal_handle is not None:
            self.get_logger().info('Cancelling navigation...')
            self._goal_handle.cancel_goal_async()


def main():
    rclpy.init()
    navigator = WaypointNavigator()

    try:
        ok = navigator.send_waypoints(WAYPOINTS)
        if ok:
            rclpy.spin(navigator)
    except KeyboardInterrupt:
        navigator.cancel()
    finally:
        navigator.destroy_node()


if __name__ == '__main__':
    main()

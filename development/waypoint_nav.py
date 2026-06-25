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

# --- Define your waypoints here (x meters, y meters, yaw degrees) ---
WAYPOINTS = [
    (1.0,  0.0,   0.0),
    (1.0,  1.0,  90.0),
    (0.0,  1.0, 180.0),
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

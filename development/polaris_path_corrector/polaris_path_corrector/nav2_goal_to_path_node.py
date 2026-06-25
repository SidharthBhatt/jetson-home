import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from nav2_msgs.action import ComputePathToPose


class Nav2GoalToPathNode(Node):
    def __init__(self):
        super().__init__('nav2_goal_to_path_node')

        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('output_path_topic', '/input_path')
        self.declare_parameter('planner_action_name', '/compute_path_to_pose')
        self.declare_parameter('planner_id', '')
        self.declare_parameter('use_start', False)

        self.path_pub = self.create_publisher(
            Path,
            self.get_parameter('output_path_topic').value,
            10
        )

        self.goal_sub = self.create_subscription(
            PoseStamped,
            self.get_parameter('goal_topic').value,
            self.goal_cb,
            10
        )

        self.client = ActionClient(
            self,
            ComputePathToPose,
            self.get_parameter('planner_action_name').value
        )

        self.get_logger().info('Waiting for Nav2 ComputePathToPose action server...')

    def goal_cb(self, msg):
        if not self.client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warn('Nav2 planner action server is not available yet.')
            return

        goal_msg = ComputePathToPose.Goal()
        goal_msg.goal = msg
        goal_msg.planner_id = self.get_parameter('planner_id').value
        goal_msg.use_start = bool(self.get_parameter('use_start').value)

        self.get_logger().info('Requesting Nav2 global path...')

        future = self.client.send_goal_async(goal_msg)
        future.add_done_callback(self.goal_response_cb)

    def goal_response_cb(self, future):
        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().warn('Nav2 path request rejected.')
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_cb)

    def result_cb(self, future):
        result = future.result().result
        path = result.path

        if len(path.poses) == 0:
            self.get_logger().warn('Nav2 returned an empty path.')
            return

        self.path_pub.publish(path)
        self.get_logger().info(f'Published /input_path with {len(path.poses)} poses.')


def main(args=None):
    rclpy.init(args=args)
    node = Nav2GoalToPathNode()

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
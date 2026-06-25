import csv
import os
from datetime import datetime

import rclpy
from rclpy.node import Node

from std_msgs.msg import String, Float32


class EventLoggerNode(Node):
    def __init__(self):
        super().__init__('event_logger_node')

        self.declare_parameter('obstacle_state_topic', '/obstacle_state')
        self.declare_parameter('safe_speed_topic', '/safe_speed')
        self.declare_parameter('log_path', '/tmp/path_corrector_events.csv')

        self.log_path = self.get_parameter('log_path').value

        self.last_state = None
        self.last_speed = 0.0

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        if not os.path.exists(self.log_path):
            myFile = open(self.log_path, 'w', newline='')
            writer = csv.writer(myFile)
            writer.writerow(['wall_time', 'ros_time_sec', 'event_type', 'state', 'safe_speed'])
            myFile.close()

        self.create_subscription(
            String,
            self.get_parameter('obstacle_state_topic').value,
            self.state_cb,
            10
        )

        self.create_subscription(
            Float32,
            self.get_parameter('safe_speed_topic').value,
            self.speed_cb,
            10
        )

        self.get_logger().info(f'Logging events to {self.log_path}')

    def speed_cb(self, msg):
        self.last_speed = msg.data

    def state_cb(self, msg):
        state = msg.data

        if state == self.last_state:
            return

        self.last_state = state

        event_type = 'state_change'

        if state.startswith('AVOID'):
            event_type = 'avoidance'
        elif state.startswith('STOP'):
            event_type = 'stop'
        elif state == 'CLEAR':
            event_type = 'clear'

        ros_time = self.get_clock().now().nanoseconds / 1000000000.0
        wall_time = datetime.now().isoformat(timespec='seconds')

        myFile = open(self.log_path, 'a', newline='')
        writer = csv.writer(myFile)
        writer.writerow([
            wall_time,
            f'{ros_time:.3f}',
            event_type,
            state,
            f'{self.last_speed:.3f}'
        ])
        myFile.close()

        self.get_logger().info(
            f'event={event_type}, state={state}, safe_speed={self.last_speed:.2f}'
        )


def main(args=None):
    rclpy.init(args=args)
    node = EventLoggerNode()

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
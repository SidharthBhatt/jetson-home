import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from sensor_msgs.msg import LaserScan, PointCloud2, PointField
from sensor_msgs_py import point_cloud2


class ScanToPointCloud(Node):
    def __init__(self):
        super().__init__('scan_to_pointcloud')

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

        self.cloud_publisher = self.create_publisher(
            PointCloud2,
            '/scan_points',
            10
        )

        self.get_logger().info('Scan to PointCloud2 converter started')

    def scan_callback(self, scan_msg):
        points = []

        angle = scan_msg.angle_min

        for distance in scan_msg.ranges:
            if not math.isinf(distance) and not math.isnan(distance):
                if scan_msg.range_min < distance < scan_msg.range_max:
                    x = distance * math.cos(angle)
                    y = distance * math.sin(angle)
                    z = 0.0

                    points.append([x, y, z])

            angle += scan_msg.angle_increment

        fields = [
            PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
        ]

        cloud_msg = point_cloud2.create_cloud(
            scan_msg.header,
            fields,
            points
        )

        self.cloud_publisher.publish(cloud_msg)

        self.get_logger().info(f'Published point cloud with {len(points)} points')


def main():
    rclpy.init()

    node = ScanToPointCloud()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

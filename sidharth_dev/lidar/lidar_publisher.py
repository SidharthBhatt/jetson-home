import rclpy
from rclpy.node import Node


'''
Termial 1: run robot bringup

1. at Terminal 1, turn on raidar
    source /opt/ros/humble/setup.bash
    source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
    ros2 launch ydlidar_ros2_driver ydlidar_launch.py


2. at terminal 2, turn on robot control access
    source /opt/ros/humble/setup.bash
    source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
    ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py


3. at terminal 3, run code
    cd ~/sidharth_dev/lidar_publisher
    python3 lidar_publisher.py

'''

class LidarPublisher(Node):

    def __init__(self):
        super().__init__('lidar_publisher')
        scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        self.scan_subscriber = self.create_subscription(LaserScan, '/scan', self.scan_callback, scan_qos)
        self.cloud_publisher_ = self.create_publisher(PointCloud2, '/scan_points', 10)


    def timer_callback(self):
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


def main(args=None):
    rclpy.init()

    lidar_publisher = LidarPublisher()

    rclpy.spin(lidar_publisher)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
     try:
        rclpy.spin(lidar_publisher)
    except KeyboardInterrupt:
        pass
    finally:
        lidar_publisher.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2

# How to use
# 
# Publisher Terminal (on laptop)
# source /opt/ros/humble/setup.bash
# cd ~/sidharth_dev/camera
# python3 image_publisher.py
# 
# View (ON YAHBOOM screen )
# DONT NEED source /opt/ros/humble/setup.bash 
# export DISPLAY=:0
# ros2 run rqt_image_view rqt_image_view


# publishes images to the /camera/image_raw topic at 30 fps

class ImageSubscriberNode(Node):
    def __init__(self):
        super().__init__('image_subscriber')
        self.sub = self.create_subscription(Image, '/camera/image_raw', self.listener_callback, 10)
        self.bridge = CvBridge()

    def listener_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        cv2.imshow("Camera Feed", frame)
        cv2.waitKey(1)


def main():
    rclpy.init()
    node = ImageSubscriberNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

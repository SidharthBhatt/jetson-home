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

class ImagePublisher(Node):
    def __init__(self):
        super().__init__('image_publisher')
        self.pub = self.create_publisher(Image, '/camera/image_raw', 10)  
        self.bridge = CvBridge()

        # Force the V4L2 backend for the USB (UVC) camera at /dev/video0.
        # Without CAP_V4L2, OpenCV may auto-pick the GStreamer or OBSENSOR
        # backend, which either prints the "Cannot query video position"
        # warning or fails to read frames.
        self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().error('Could not open /dev/video0')
            raise RuntimeError('camera open failed')

        # MJPG + a small resolution = fast capture. The camera defaults to
        # 2048x1536, which only delivers ~2 Hz because each raw bgr8 frame
        # is ~9 MB. 640x480 MJPG runs a true 30 fps.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.get_logger().info(f'camera opened at {w}x{h}')

        self.timer = self.create_timer(0.033, self.tick)   # 30 Hz
        self.counter = 0
    def tick(self):
        ok, frame = self.cap.read()
        if (self.counter % 30 == 0):
            self.get_logger().info(f'Publishing frame {self.counter}')
        self.counter = self.counter + 1
        if not ok:
            self.get_logger().warn('no frame')
            return
        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera'
        self.pub.publish(msg)
    def publish_for_one_second(self):
        for i in range(30):
            self.tick()

def main():
    rclpy.init()
    node = ImagePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cap.release()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

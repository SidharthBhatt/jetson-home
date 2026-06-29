import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


'''
source /opt/ros/humble/setup.bash
cd ~/sidharth_dev/data_pipeline
python3 uncanner.py
'''
# 1. Open the bag (point at the DIRECTORY, not the .db3)
reader = rosbag2_py.SequentialReader()
reader.open(
    rosbag2_py.StorageOptions(uri="rosbag2_2026_06_30-04_36_03", storage_id="sqlite3"),
    rosbag2_py.ConverterOptions("", ""),
)

bridge = CvBridge()
count = 0
while reader.has_next():
    topic, data, t_nanosec = reader.read_next()   # data = raw CDR bytes
    if topic == "/camera/image_raw":
        msg = deserialize_message(data, Image)      # step 2: bytes -> Image
        frame = bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")  # step 3a
        print("image at t_nanosec")
        # cv2.imwrite(f"frame_{t_nanosec}.png", frame)                # step 3b
        count += 1
print(f"wrote {count} images")
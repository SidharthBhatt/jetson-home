import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import time


'''
what is this code doing?

1. move front
2. move back
3. left turn while moving front
4. right turn while moving left
5. stop

How to tun the demo:
1. At terminal 1, run robot bringup
    source /opt/ros/humble/setup.bash
    source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
    ros2 launch yahboomcar_bringup yahboomcar_bringup_R2_launch.py



2. At terminal 2, run the demo
    source /opt/ros/humble/setup.bash
    source ~/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
    cd ~/development/movement_demo
    python3 move_robot_demo.py


'''
class TestMotors(Node):
    def __init__(self):
        super().__init__('test_motors')
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)

        self.publish_rate = 0.5
        
        time.sleep(1.0)

    def publish_cmd_vel(self, linear_x, angular_z, duration):
        msg = Twist()

        msg.linear.x = linear_x
        msg.linear.y = 0.0
        msg.linear.z = 0.0

        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = angular_z

        start_time = time.time()

        while time.time() - start_time < duration:
            self.publisher.publish(msg)
            time.sleep(1.0 / self.publish_rate)

        self.stop()

    def stop(self):
        msg = Twist()

        msg.linear.x = 0.0
        msg.linear.y = 0.0
        msg.linear.z = 0.0

        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = 0.0

        for i in range(5):
            self.publisher.publish(msg)
            time.sleep(0.1)

    def move_forward(self, distance, speed):
        duration = abs(distance) / abs(speed)

        print("Move forward")
        print("Target distance:", distance, "meters")
        print("Speed:", speed, "m/s")
        print("Duration:", duration, "seconds")
        print("Command: linear.x =", speed, ", angular.z = 0.0")

        self.publish_cmd_vel(speed, 0.0, duration)

    def move_backward(self, distance, speed):
        duration = abs(distance) / abs(speed)
        backward_speed = -abs(speed)

        print("Move backward")
        print("Target distance:", distance, "meters")
        print("Speed:", backward_speed, "m/s")
        print("Duration:", duration, "seconds")
        print("Command: linear.x =", backward_speed, ", angular.z = 0.0")

        self.publish_cmd_vel(backward_speed, 0.0, duration)

    def curve_left(self, speed, turn_rate, duration):
        print("Curve left")
        print("Speed:", speed, "m/s")
        print("Turn rate:", turn_rate, "rad/s")
        print("Duration:", duration, "seconds")
        print("Command: linear.x =", speed, ", angular.z =", turn_rate)

        self.publish_cmd_vel(speed, turn_rate, duration)

    def curve_right(self, speed, turn_rate, duration):
        right_turn_rate = -abs(turn_rate)

        print("Curve right")
        print("Speed:", speed, "m/s")
        print("Turn rate:", right_turn_rate, "rad/s")
        print("Duration:", duration, "seconds")
        print("Command: linear.x =", speed, ", angular.z =", right_turn_rate)

        self.publish_cmd_vel(speed, right_turn_rate, duration)

    def drive_custom(self, speed, turn_rate, duration):
        print("Custom drive")
        print("Speed:", speed, "m/s")
        print("Turn rate:", turn_rate, "rad/s")
        print("Duration:", duration, "seconds")
        print("Command: linear.x =", speed, ", angular.z =", turn_rate)

        self.publish_cmd_vel(speed, turn_rate, duration)


def main():
    rclpy.init()

    robot = TestMotors()

    print("Starting movement demo")



    # Modify values here

    forward_distance = 1.0
    backward_distance = 1.0

    forward_speed = 0.15
    backward_speed = 0.15

    left_curve_speed = 0.15
    left_turn_rate = 0.2
    left_curve_duration = 2.0

    right_curve_speed = 0.15
    right_turn_rate = 0.2
    right_curve_duration = 2.0

    wait_between_demos = 1.0

 


    # Demo sequence

    print("Demo 1: forward")
    robot.move_backward(forward_distance, forward_speed)
    time.sleep(wait_between_demos)

    print("Demo 2: backward")
    robot.move_backward(backward_distance, backward_speed)
    time.sleep(wait_between_demos)

    print("Demo 3: forward curve left")
    robot.curve_left(left_curve_speed, left_turn_rate, left_curve_duration)
    time.sleep(wait_between_demos)

    print("Demo 4: forward curve right")
    robot.curve_right(right_curve_speed, right_turn_rate, right_curve_duration)
    time.sleep(wait_between_demos)

    print("Demo 5: stop")
    robot.stop()

    robot.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
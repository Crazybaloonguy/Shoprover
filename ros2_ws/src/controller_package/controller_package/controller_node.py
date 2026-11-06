import math

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import LaserScan

class ControllerNode(Node):

    def __init__(self):
        super().__init__('controller_node')
        print("Controller Node Initialized")
        self.subscription = self.create_subscription(
            LaserScan,
            '/scan', # Lidar scan
            self.rplidar_callback,
            10)
        self.subscription  # prevent unused variable warning

    def rplidar_callback(self, msg):
        obstacles = [
            (distance, math.degrees(angle))
            for index, distance in enumerate(msg.ranges)
            for angle in [msg.angle_min + index * msg.angle_increment]
            if -math.pi / 6 <= angle <= math.pi / 6
            and msg.range_min <= distance < 0.5
            and math.isfinite(distance)
        ]
        obstacle_detected = bool(obstacles)

        if obstacle_detected:
            closest_distance, closest_angle = min(obstacles)
            self.get_logger().warn(
                f'Hindernis bei {closest_distance:.2f} m '
                f'bei {closest_angle:.1f} Grad')


def main(args=None):
    rclpy.init(args=args)
    node = ControllerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
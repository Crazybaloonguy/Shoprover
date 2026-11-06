import rclpy
from rclpy.node import Node

from libs.hover_serial import Hoverboard_serial
from std_msgs.msg import String


class MotorController(Node):

    def __init__(self):
        super().__init__('motor_controller')
        self.subscription = self.create_subscription(
            String,
            'topic',
            self.listener_callback,
            10)
        self.subscription  # prevent unused variable warning

    def listener_callback(self, msg):
        self.get_logger().info('I heard: "%s"' % msg.data)


def main(args=None):
    rclpy.init(args=args)

    motor_controller = MotorController()

    rclpy.spin(motor_controller)

    motor_controller.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

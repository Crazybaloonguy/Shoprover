import rclpy
from rclpy.node import Node

from std_msgs.msg import String

class ControllerNode(Node):

    def __init__(self):
        super().__init__('controller_node')
        print("Controller Node Initialized")
        self.subscription = self.create_subscription(
            String,
            'scan',
            self.listener_callback,
            10)
        self.subscription  # prevent unused variable warning

    def listener_callback(self, msg):
        self.get_logger().info('I heard: "%s"' % msg.data)
        # Hier können Sie die Logik implementieren, um die Daten zu verarbeiten und den Roboter zu steuern.
        # Zum Beispiel könnten Sie die Daten analysieren und entsprechende Steuerbefehle senden.
        # self.send_control_command(processed_data)  # Beispiel für das Senden von Steuerbefehlen


def main(args=None):
    rclpy.init(args=args)
    node = ControllerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
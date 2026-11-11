"""
Publishes the data of the UWB anchors to ROS 2.

Topics:
  uwb/status           std_msgs/String            state of the UWB link (latched)
  uwb/anchors          std_msgs/UInt16MultiArray  addresses of the anchors registered
                                                  at the tag (latched)
  uwb/goal_coordinate  geometry_msgs/PointStamped position of the tag in m relative
                                                  to the vehicle (frame base_link,
                                                  point.x / point.y, z = 0); sent once
                                                  every anchor has a new distance

Latched = transient local: nodes started later still get the last value.
"""
from geometry_msgs.msg import PointStamped
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String, UInt16MultiArray


class UwbPublisher:

    def __init__(self, node):
        self._node = node
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._status_pub = node.create_publisher(String, 'uwb/status', latched)
        self._anchors_pub = node.create_publisher(UInt16MultiArray, 'uwb/anchors', latched)
        self._goal_coordinate_pub = node.create_publisher(PointStamped, 'uwb/goal_coordinate', 10)

    def publish_status(self, text):
        msg = String()
        msg.data = text
        self._status_pub.publish(msg)
        self._node.get_logger().info(text)

    def publish_anchors(self, addresses):
        msg = UInt16MultiArray()
        msg.data = list(addresses)
        self._anchors_pub.publish(msg)

    def publish_coordinates(self, pos):
        """pos: (x, y) of the tag in m, relative to the vehicle"""
        msg = PointStamped()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.point.x, msg.point.y = float(pos[0]), float(pos[1])
        self._goal_coordinate_pub.publish(msg)

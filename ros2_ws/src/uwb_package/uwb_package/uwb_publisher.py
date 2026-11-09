"""
Publishes the data of the UWB anchors to ROS 2.

Topics (both latched: transient local, so nodes started later still get
the last value):
  uwb/status   std_msgs/String           state of the UWB link
  uwb/anchors  std_msgs/UInt16MultiArray addresses of the anchors registered
                                         at the tag

Distances are not published yet; a publisher for them goes here once the
ranging is implemented.
"""

from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String, UInt16MultiArray


class UwbPublisher:

    def __init__(self, node):
        self._node = node
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._status_pub = node.create_publisher(String, 'uwb/status', latched)
        self._anchors_pub = node.create_publisher(UInt16MultiArray, 'uwb/anchors', latched)

    def publish_status(self, text):
        msg = String()
        msg.data = text
        self._status_pub.publish(msg)
        self._node.get_logger().info(text)

    def publish_anchors(self, addresses):
        msg = UInt16MultiArray()
        msg.data = list(addresses)
        self._anchors_pub.publish(msg)

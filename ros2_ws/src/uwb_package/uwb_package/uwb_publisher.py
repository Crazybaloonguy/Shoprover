"""
Publishes the data of the UWB anchors to ROS 2.

Topics:
  uwb/status     std_msgs/String            state of the UWB link (latched)
  uwb/anchors    std_msgs/UInt16MultiArray  addresses of the anchors registered
                                            at the tag (latched)
  uwb/distances  std_msgs/Float32MultiArray latest distance tag <-> anchor in m,
                                            one entry per anchor in the order
                                            of uwb/anchors (NaN = none yet);
                                            sent after every new measurement

Latched = transient local: nodes started later still get the last value.
"""

from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Float32MultiArray, String, UInt16MultiArray


class UwbPublisher:

    def __init__(self, node):
        self._node = node
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._status_pub = node.create_publisher(String, 'uwb/status', latched)
        self._anchors_pub = node.create_publisher(UInt16MultiArray, 'uwb/anchors', latched)
        self._distances_pub = node.create_publisher(Float32MultiArray, 'uwb/distances', 10)

    def publish_status(self, text):
        msg = String()
        msg.data = text
        self._status_pub.publish(msg)
        self._node.get_logger().info(text)

    def publish_anchors(self, addresses):
        msg = UInt16MultiArray()
        msg.data = list(addresses)
        self._anchors_pub.publish(msg)

    def publish_distances(self, distances):
        msg = Float32MultiArray()
        msg.data = [float(d) for d in distances]
        self._distances_pub.publish(msg)

"""
Publishes the data of the UWB anchors to ROS 2.

Topics:
  uwb/status    std_msgs/String            state of the UWB link (latched)
  uwb/anchors   std_msgs/UInt16MultiArray  addresses of the anchors registered
                                           at the tag (latched)
  goal_update   geometry_msgs/PoseStamped  position of the tag, transformed into a fixed
                                           frame (parameter goal_frame, e.g. odom or map);
                                           orientation points from the vehicle to the tag.
                                           Goal for the GoalUpdater of Nav2's follow_point.xml
                                           behavior tree (topic name: parameter goal_topic)

Latched = transient local: nodes started later still get the last value.

The goal for Nav2 must be in a fixed frame: a goal in base_link would move
with the vehicle. The stamp is the current time, because the GoalUpdater
ignores goals older than the current one.
"""
import math

import rclpy.time
from geometry_msgs.msg import PoseStamped
from rclpy.duration import Duration
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import UInt16MultiArray
from tf2_ros import Buffer, TransformListener
import tf2_geometry_msgs  # noqa: F401  registers PoseStamped for Buffer.transform


class UwbPublisher:

    TF_TIMEOUT = Duration(seconds=0.2)

    def __init__(self, node, goal_frame='odom', goal_topic='goal_update'):
        self._node = node
        self._goal_frame = goal_frame
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._anchors_pub = node.create_publisher(UInt16MultiArray, 'uwb/anchors', latched)
        self._goal_pub = node.create_publisher(PoseStamped, goal_topic, 10)
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, node)

    def publish_anchors(self, addresses):
        msg = UInt16MultiArray()
        msg.data = list(addresses)
        self._anchors_pub.publish(msg)

    def publish_coordinates(self, pos):
        """pos: (x, y) of the tag in m, relative to the vehicle (base_link)"""
        msg = PoseStamped()
        msg.header.frame_id = 'base_link'
        msg.header.stamp = rclpy.time.Time().to_msg()   # 0 = latest available transform
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = float(pos[0]), float(pos[1]), 0.0
        yaw = math.atan2(pos[1], pos[0])
        msg.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.orientation.w = math.cos(yaw / 2.0)
        try:
            goal = self._tf_buffer.transform(msg, self._goal_frame, timeout=self.TF_TIMEOUT)
        except Exception as e:
            self._node.get_logger().warning('no transform base_link -> %s, goal not sent: %s'
                                            % (self._goal_frame, e))
            return
        goal.header.stamp = self._node.get_clock().now().to_msg()
        self._goal_pub.publish(goal)

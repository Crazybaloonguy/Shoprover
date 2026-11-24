"""
Publishes the data of the UWB anchors to ROS 2.

Topics:
  uwb/anchors   std_msgs/UInt16MultiArray  addresses of the anchors registered
                                           at the tag (latched)
  goal_update   geometry_msgs/PoseStamped  position of the tag in a fixed frame
                                           (parameter goal_frame, e.g. odom or map);
                                           orientation points from the vehicle to the tag.
                                           Goal for the GoalUpdater of Nav2's follow_point.xml
                                           behavior tree (topic name: parameter goal_topic)

Latched = transient local: nodes started later still get the last value.

The goal for Nav2 must be in a fixed frame: a goal in base_link would move
with the vehicle. Every measured position is therefore transformed into the
fixed frame right when it is measured (to_goal_frame), with the pose of the
vehicle at that moment; the filter then runs on positions in the fixed frame.
The stamp of the goal is the current time, because the GoalUpdater ignores
goals older than the current one.
"""
import math

import rclpy.time
from geometry_msgs.msg import PoseStamped
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import UInt16MultiArray
from tf2_ros import Buffer, TransformListener


class UwbPublisher:

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

    def to_goal_frame(self, pos):
        """
        pos: (x, y) of the tag in m relative to the vehicle (base_link), just measured
        -> ((x, y) of the tag, (x, y) of the vehicle), both in goal_frame,
           or None if the transform is missing
        """
        try:
            # Time() = 0: latest available transform, i.e. the pose of the vehicle now.
            # No timeout: waiting would not give a newer pose, and while the
            # transform is missing the rounds would pile up behind the wait.
            tf = self._tf_buffer.lookup_transform(self._goal_frame, 'base_link', rclpy.time.Time())
        except Exception as e:
            self._node.get_logger().warning('no transform base_link -> %s, point dropped: %s'
                                            % (self._goal_frame, e), throttle_duration_sec=2.0)
            return None
        t, q = tf.transform.translation, tf.transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        c, s = math.cos(yaw), math.sin(yaw)
        tag = (t.x + c * pos[0] - s * pos[1],
               t.y + s * pos[0] + c * pos[1])
        return tag, (t.x, t.y)

    def publish_goal(self, tag, vehicle):
        """tag, vehicle: (x, y) in goal_frame; orientation points from the vehicle to the tag"""
        msg = PoseStamped()
        msg.header.frame_id = self._goal_frame
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = float(tag[0]), float(tag[1]), 0.0
        yaw = math.atan2(tag[1] - vehicle[1], tag[0] - vehicle[0])
        msg.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.orientation.w = math.cos(yaw / 2.0)
        self._goal_pub.publish(msg)

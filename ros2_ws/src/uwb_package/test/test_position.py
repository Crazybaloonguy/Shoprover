"""
Tests for the position of the tag in UwbNode: trilateration
(get_coordinates) and the Kalman filter (kalman). No DW3000, no ROS
needed: the node object is created without __init__, so no worker
thread starts and no SPI/GPIO is touched. If rclpy or the message
packages are missing (e.g. on a PC without ROS), they are replaced by
empty stand-ins, the tested methods do not use them.

Run from ros2_ws/src/uwb_package:

    python3 -m unittest discover -s test -v      # without pytest
    python3 -m pytest test -v                    # with pytest
    colcon test --packages-select uwb_package    # from ros2_ws
"""

import math
import os
import random
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def _stub_ros():
    """Empty stand-ins for the ROS modules uwb_node imports, if ROS is not installed."""
    try:
        import rclpy  # noqa: F401
        return
    except ImportError:
        pass
    stubs = {
        'rclpy': {},
        'rclpy.executors': {'ExternalShutdownException': Exception},
        'rclpy.node': {'Node': object},
        'rclpy.qos': {'DurabilityPolicy': object, 'QoSProfile': object},
        'geometry_msgs': {},
        'geometry_msgs.msg': {'PointStamped': object},
        'std_msgs': {},
        'std_msgs.msg': {'String': object, 'UInt16MultiArray': object},
    }
    for name, attrs in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module


_stub_ros()
from uwb_package.uwb_node import UwbNode  # noqa: E402

# Same as anchor_positions in launch/uwb.launch.py, keep both in sync.
ANCHORS = [(0.45, 0.0), (-0.5, 0.5), (-0.5, -0.5)]


def make_node(anchors=ANCHORS):
    node = UwbNode.__new__(UwbNode)     # skip __init__: no ROS, no hardware
    node.positions = list(anchors)
    return node


def distances_to(x, y, anchors=ANCHORS):
    """Exact distances from the point (x, y) to every anchor."""
    return [math.hypot(x - ax, y - ay) for ax, ay in anchors]


class TestGetCoordinates(unittest.TestCase):

    def test_exact_distances_give_the_true_position(self):
        node = make_node()
        for x, y in [(2.0, 0.0), (1.0, 1.0), (-1.5, 0.3), (0.0, -2.0), (5.0, 3.0), (0.1, 0.1)]:
            with self.subTest(tag=(x, y)):
                pos = node.get_coordinates(distances_to(x, y))
                self.assertIsNotNone(pos)
                self.assertAlmostEqual(pos[0], x, places=6)
                self.assertAlmostEqual(pos[1], y, places=6)

    def test_tag_on_an_anchor(self):
        node = make_node()
        pos = node.get_coordinates(distances_to(*ANCHORS[1]))
        self.assertAlmostEqual(pos[0], ANCHORS[1][0], places=6)
        self.assertAlmostEqual(pos[1], ANCHORS[1][1], places=6)

    def test_anchors_on_one_line_give_none(self):
        line = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)]
        node = make_node(line)
        self.assertIsNone(node.get_coordinates(distances_to(2.0, 1.0, line)))

    def test_small_distance_error_gives_small_position_error(self):
        # 2 cm error on one distance must not move a tag 2 m away by more than 20 cm
        node = make_node()
        d = distances_to(2.0, 0.0)
        d[0] += 0.02
        x, y = node.get_coordinates(d)
        self.assertLess(math.hypot(x - 2.0, y - 0.0), 0.2)


class TestKalman(unittest.TestCase):

    def test_constant_points_stay_unchanged(self):
        node = make_node()
        x, y = node.kalman([(1.5, -0.7)] * UwbNode.POINTS_PER_BATCH)
        self.assertAlmostEqual(x, 1.5)
        self.assertAlmostEqual(y, -0.7)

    def test_single_point_is_returned(self):
        node = make_node()
        self.assertEqual(node.kalman([(1.0, 2.0)]), (1.0, 2.0))

    def test_noise_is_reduced(self):
        # many batches of noisy points around a fixed position:
        # the filtered results must scatter less than the single points
        node = make_node()
        rng = random.Random(42)
        true_x, true_y, noise = 2.0, 0.5, 0.1
        raw_err, filtered_err = [], []
        for _ in range(500):
            batch = [(true_x + rng.gauss(0, noise), true_y + rng.gauss(0, noise))
                     for _ in range(UwbNode.POINTS_PER_BATCH)]
            fx, fy = node.kalman(batch)
            raw_err.append(math.hypot(batch[-1][0] - true_x, batch[-1][1] - true_y))
            filtered_err.append(math.hypot(fx - true_x, fy - true_y))
        raw_rms = math.sqrt(sum(e * e for e in raw_err) / len(raw_err))
        filtered_rms = math.sqrt(sum(e * e for e in filtered_err) / len(filtered_err))
        print('\n  noise %.2f m: raw rms %.3f m, filtered rms %.3f m'
              % (noise, raw_rms, filtered_rms))
        self.assertLess(filtered_rms, 0.75 * raw_rms)

    def test_moving_tag_result_is_close_to_newest_point(self):
        # tag walks 10 cm per point from x = 1.0 to x = 1.9:
        # the result must lie nearer the newest point than the batch mean
        node = make_node()
        batch = [(1.0 + 0.1 * i, 0.0) for i in range(UwbNode.POINTS_PER_BATCH)]
        x, _ = node.kalman(batch)
        mean_x = sum(p[0] for p in batch) / len(batch)
        self.assertGreater(x, mean_x)
        self.assertLessEqual(x, batch[-1][0])


class TestTrilaterationAndFilter(unittest.TestCase):

    def test_noisy_distances_end_up_near_the_true_position(self):
        # whole chain as in the node: noisy distances -> get_coordinates -> kalman
        node = make_node()
        rng = random.Random(7)
        true_x, true_y = 1.5, 0.5
        batch = []
        for _ in range(UwbNode.POINTS_PER_BATCH):
            d = [di + rng.gauss(0, 0.02) for di in distances_to(true_x, true_y)]
            batch.append(node.get_coordinates(d))
        x, y = node.kalman(batch)
        print('\n  tag at (%.2f, %.2f) -> filtered (%.2f, %.2f)' % (true_x, true_y, x, y))
        self.assertLess(math.hypot(x - true_x, y - true_y), 0.15)


if __name__ == '__main__':
    unittest.main(verbosity=2)

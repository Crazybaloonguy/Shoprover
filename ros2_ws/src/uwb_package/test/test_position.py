"""
Tests for the position of the tag in UwbNode: trilateration
(get_coordinates, with the estimated height of the tag) and the
Kalman filter (kalman). No DW3000, no ROS
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
        'rclpy.time': {'Time': object},
        'rclpy.qos': {'DurabilityPolicy': object, 'QoSProfile': object},
        'geometry_msgs': {},
        'geometry_msgs.msg': {'PoseStamped': object},
        'std_msgs': {},
        'std_msgs.msg': {'UInt16MultiArray': object},
        'tf2_ros': {'Buffer': object, 'TransformListener': object},
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
    node._h2, node._height_rounds = 0.0, 0                   # set in __init__
    node._kf_pos, node._kf_var, node._kf_time = None, 0.0, 0.0
    node.get_logger = lambda: types.SimpleNamespace(info=lambda *a: None)
    return node


def distances_to(x, y, anchors=ANCHORS, h=0.0):
    """Exact distances from the point (x, y) to every anchor, tag h higher than the anchors."""
    return [math.sqrt((x - ax) ** 2 + (y - ay) ** 2 + h * h) for ax, ay in anchors]


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


class TestHeight(unittest.TestCase):

    def test_height_is_estimated_and_position_stays_right(self):
        # tag 1.1 m above the anchors, noisy distances: after many rounds the
        # estimated height must be close, the positions must not be biased
        node = make_node()
        rng = random.Random(3)
        true_h, err = 1.1, []
        for _ in range(500):
            x, y = rng.uniform(1.5, 4.0), rng.uniform(-1.5, 1.5)
            d = [di + rng.gauss(0, 0.03) for di in distances_to(x, y, h=true_h)]
            px, py = node.get_coordinates(d)
            err.append((px - x, py - y))
        self.assertAlmostEqual(math.sqrt(node._h2), true_h, delta=0.15)
        mean_x = sum(e[0] for e in err[100:]) / len(err[100:])
        mean_y = sum(e[1] for e in err[100:]) / len(err[100:])
        self.assertLess(math.hypot(mean_x, mean_y), 0.05)

    def test_exact_distances_with_height_give_the_true_position(self):
        node = make_node()
        for _ in range(UwbNode.HEIGHT_MIN_ROUNDS + 5):     # also after the fit is used
            pos = node.get_coordinates(distances_to(2.0, 0.5, h=0.9))
            self.assertAlmostEqual(pos[0], 2.0, places=5)
            self.assertAlmostEqual(pos[1], 0.5, places=5)


DT = 0.1    # time between two rounds in the tests, s (~10 rounds/s)


def run_filter(node, points, dt=DT):
    """Feed points into node.kalman, DT apart -> list of filtered (x, y)."""
    return [node.kalman(p, i * dt) for i, p in enumerate(points)]


class TestKalman(unittest.TestCase):

    def test_first_point_is_returned(self):
        node = make_node()
        self.assertEqual(node.kalman((1.0, 2.0), 0.0), (1.0, 2.0))

    def test_constant_points_stay_unchanged(self):
        node = make_node()
        x, y = run_filter(node, [(1.5, -0.7)] * 20)[-1]
        self.assertAlmostEqual(x, 1.5)
        self.assertAlmostEqual(y, -0.7)

    def test_noise_is_reduced(self):
        # noisy points around a fixed position, filter keeps running:
        # the filtered results must scatter less than the single points
        node = make_node()
        rng = random.Random(42)
        true_x, true_y, noise = 2.0, 0.5, 0.1
        points = [(true_x + rng.gauss(0, noise), true_y + rng.gauss(0, noise)) for _ in range(2000)]
        out = run_filter(node, points)[100:]            # after the start
        raw_rms = math.sqrt(sum((p[0] - true_x) ** 2 + (p[1] - true_y) ** 2
                                for p in points[100:]) / len(out))
        filtered_rms = math.sqrt(sum((p[0] - true_x) ** 2 + (p[1] - true_y) ** 2
                                     for p in out) / len(out))
        print('\n  noise %.2f m: raw rms %.3f m, filtered rms %.3f m'
              % (noise, raw_rms, filtered_rms))
        self.assertLess(filtered_rms, 0.75 * raw_rms)

    def test_follows_a_moving_tag(self):
        # tag walks 0.5 m/s along x: the filter lags behind, but stays close
        node = make_node()
        points = [(1.0 + 0.5 * i * DT, 0.0) for i in range(100)]
        x, _ = run_filter(node, points)[-1]
        self.assertLess(x, points[-1][0])
        self.assertGreater(x, points[-1][0] - 0.5)

    def test_long_gap_trusts_the_new_point(self):
        # no point for 30 s (e.g. tag lost): the next point counts almost fully
        node = make_node()
        run_filter(node, [(0.0, 0.0)] * 20)
        x, y = node.kalman((3.0, 1.0), 20 * DT + 30.0)
        self.assertGreater(x, 2.9)
        self.assertGreater(y, 0.95)


class TestTrilaterationAndFilter(unittest.TestCase):

    def test_noisy_distances_end_up_near_the_true_position(self):
        # whole chain as in the node: noisy distances -> get_coordinates -> kalman
        node = make_node()
        rng = random.Random(7)
        true_x, true_y = 1.5, 0.5
        for i in range(50):
            d = [di + rng.gauss(0, 0.02) for di in distances_to(true_x, true_y, h=0.8)]
            x, y = node.kalman(node.get_coordinates(d), i * DT)
        print('\n  tag at (%.2f, %.2f) -> filtered (%.2f, %.2f)' % (true_x, true_y, x, y))
        self.assertLess(math.hypot(x - true_x, y - true_y), 0.15)


if __name__ == '__main__':
    unittest.main(verbosity=2)

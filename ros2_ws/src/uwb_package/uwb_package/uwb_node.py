"""
ROS 2 node for the UWB anchors on the Raspberry Pi.

Each anchor is one DW3000 on the shared SPI bus: the i-th address in
anchor_addresses belongs to device i (the i-th CS pin in
driver/dw_platform/port.py). On start the node initialises these devices
and registers each anchor at the tag (handshake, see driver/handshake.py).
After that the tag ranges the anchors one after the other (DS-TWR, see
driver/ranging.py); each anchor computes its distance to the tag. Once
every anchor has a new distance, the position of the tag (x/y relative to
the vehicle) is computed by trilateration and published on
uwb/goal_coordinate. The DW3000 work runs in a worker
thread, so the node keeps spinning while it waits for the tag. Progress
and results go out through UwbPublisher.

Parameters:
  anchor_addresses  addresses of the anchors, one per DW3000, e.g. [1, 2, 3]
                    (default [1])
  anchor_positions  x/y of each anchor in m relative to the vehicle, flat:
                    [x0, y0, x1, y1, ...], same order as anchor_addresses
"""

import math
import threading

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from uwb_package import uwb_driver
from uwb_package.uwb_publisher import UwbPublisher


class UwbNode(Node):

    POINTS_PER_BATCH = 10   # positions collected before the filter runs and the result is sent
    KALMAN_R = 0.1 ** 2     # measurement noise: variance of one position in m^2 (here +-10 cm)
    KALMAN_Q = 0.05 ** 2    # process noise: how far the tag may move between two points, m^2

    def __init__(self):
        super().__init__('uwb_node')
        self.declare_parameter('anchor_addresses', [1])
        self.declare_parameter('anchor_positions', [0.0, 0.0])

        self.uwb_publisher = UwbPublisher(self)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        anchors = list(self.get_parameter('anchor_addresses').value)
        if not anchors:
            self.uwb_publisher.publish_status('error: parameter anchor_addresses is empty')
            return
        flat = list(self.get_parameter('anchor_positions').value)
        if len(flat) != 2 * len(anchors):
            self.uwb_publisher.publish_status(
            'error: anchor_positions needs %d values (x, y per anchor), got %d'
            % (2 * len(anchors), len(flat)))
            return
        self.positions = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
        try:
            self.uwb_publisher.publish_status('initialising %d DW3000' % len(anchors))
            uwb_driver.init_dw3000(len(anchors))
            from uwb_package.driver.handshake import register_with_tag

            registered = [] # make sure the tag is running first, otherwise the anchors will never register
            for device, addr in enumerate(anchors):
                uwb_driver.select_device(device)
                self.uwb_publisher.publish_status('anchor 0x%04X: registering at the tag' % addr)
                tag_addr = None
                while tag_addr is None:
                    if self._stop.is_set():
                        return
                    tag_addr = register_with_tag(addr, max_tries=1)
                registered.append(addr)
                self.uwb_publisher.publish_anchors(registered)
                self.uwb_publisher.publish_status(
                    'anchor 0x%04X: registered at tag 0x%04X' % (addr, tag_addr))

            self.uwb_publisher.publish_status('ready: anchors %s registered at tag 0x%04X' % (
                ', '.join('0x%04X' % a for a in registered), tag_addr))

            self._handle_events(anchors)
        except Exception as e:
            self.get_logger().error('UWB failed: %s' % e)
            self.uwb_publisher.publish_status('error: %s' % e)

    def _handle_events(self, anchors):
        """
        Listen on all anchors: log and publish every distance measured by
        the tag's ranging, and log text messages (e.g. the tag's
        "Hallo <address>" test, see driver/handshake.py).
        """
        from uwb_package.driver import commmunication_utils as cu

        distances = [float('nan')] * len(anchors)
        points = []
        while True:
            event = uwb_driver.receive_event(anchors, self._stop)
            if event is None:
                return
            if event[0] == 'range':
                _, device, tag_addr, distance = event
                if distance is None:
                    self.get_logger().warning('anchor 0x%04X (DW3000 %d): ranging with tag 0x%04X failed'
                                              % (anchors[device], device, tag_addr))
                    continue
                distances[device] = distance
                self.get_logger().info('anchor 0x%04X (DW3000 %d): distance to tag 0x%04X: %.2f m'
                                       % (anchors[device], device, tag_addr, distance))
                if device == len(anchors) - 1 and not any(math.isnan(d) for d in distances):
                    pos = self.get_coordinates(distances)
                    if pos is not None:
                        points.append(pos)
                        if len(points) == self.POINTS_PER_BATCH:
                            self.uwb_publisher.publish_coordinates(self.kalman(points))
                            points = []                              # start a new batch
                    distances = [float('nan')] * len(anchors)        # start a new round
            else:
                _, device, (code, src, dest, payload) = event
                if code == cu.MSG_TEXT:
                    self.get_logger().info('anchor 0x%04X (DW3000 %d) got from tag 0x%04X: "%s"' % (
                        anchors[device], device, src, payload.decode('utf-8', 'replace')))

    def destroy_node(self):
        self._stop.set()
        self._worker.join(timeout=2.0)
        uwb_driver.shutdown()
        super().destroy_node()

    def get_coordinates(self, distances):
        """distances: [d, ...] in m -> (x, y) or None"""
        (x0, y0), d0 = self.positions[0], distances[0]
        a11 = a12 = a22 = b1 = b2 = 0.0
        for (xi, yi), di in zip(self.positions[1:], distances[1:]):
            ax, ay = 2 * (xi - x0), 2 * (yi - y0)
            b = d0**2 - di**2 + xi**2 - x0**2 + yi**2 - y0**2
            a11 += ax * ax; a12 += ax * ay; a22 += ay * ay
            b1 += ax * b;   b2 += ay * b
        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-9:          # anchors on one line -> no unique solution
            return None
        return ((a22 * b1 - a12 * b2) / det,
                (a11 * b2 - a12 * b1) / det)
    
    def kalman(self, points):
        """
        Kalman filter over one batch of positions, x and y filtered
        separately. Model: the tag stays where it is, but may move a little
        between two points (process noise KALMAN_Q). Each point is a
        measurement with noise KALMAN_R.

        points: [(x, y), ...] oldest first -> filtered (x, y) of the newest point
        """
        return (self._kalman_1d([p[0] for p in points]),
                self._kalman_1d([p[1] for p in points]))

    def _kalman_1d(self, values):
        estimate = values[0]          # start at the first measurement ...
        variance = self.KALMAN_R      # ... which is as uncertain as any measurement
        for z in values[1:]:
            variance += self.KALMAN_Q                  # predict: the tag may have moved
            gain = variance / (variance + self.KALMAN_R)
            estimate += gain * (z - estimate)          # update: move towards the measurement
            variance *= 1 - gain
        return estimate


def main(args=None):
    rclpy.init(args=args)

    uwb_node = UwbNode()

    try:
        rclpy.spin(uwb_node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        uwb_node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

"""
ROS 2 node for the UWB anchors on the Raspberry Pi.

Each anchor is one DW3000 on the shared SPI bus: the i-th address in
anchor_addresses belongs to device i (the i-th CS pin in
driver/dw_platform/port.py). On start the node initialises these devices
and registers each anchor at the tag (handshake, see driver/handshake.py).
After that the tag ranges the anchors one after the other (DS-TWR, see
driver/ranging.py); each anchor computes its distance to the tag. Once
every anchor has a new distance, the position of the tag (x/y relative to
the vehicle) is computed by trilateration (the unknown height of the tag
is estimated on the way, see get_coordinates) and transformed into the
fixed frame goal_frame with the current pose of the vehicle (TF). There it
goes through a Kalman filter after every round; every publish_period the
filtered position is published on goal_update (goal for Nav2), so it is
based on all rounds since (~10 at 20 rounds/s). The DW3000 work runs in a worker
thread, so the node keeps spinning while it waits for the tag. Progress
and results go out through UwbPublisher.

Parameters:
  anchor_addresses  addresses of the anchors, one per DW3000, e.g. [1, 2, 3]
                    (default [1])
  anchor_positions  x/y of each anchor in m relative to the vehicle, flat:
                    [x0, y0, x1, y1, ...], same order as anchor_addresses
  goal_frame        fixed frame the goal for Nav2 is published in (default odom)
  goal_topic        topic of the goal for Nav2 (default goal_update, the topic
                    the GoalUpdater in Nav2's follow_point.xml listens on)
  publish_period    s between two goals on goal_topic (default 0.5)
"""

import math
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from uwb_package import uwb_driver
from uwb_package.uwb_publisher import UwbPublisher


class UwbNode(Node):

    KALMAN_R = 0.1 ** 2     # measurement noise: variance of one position in m^2 (here +-10 cm)
    KALMAN_Q = 0.025        # process noise: how much the tag may move, m^2 per second
                            # (= (0.16 m)^2 in 1 s, (0.035 m)^2 between two rounds at 20/s)
    STATS_PERIOD = 5.0      # s between two log lines with the slack of the responses
    HEIGHT_ALPHA = 0.02     # weight of a new round in the running average of the tag's height
    HEIGHT_MIN_ROUNDS = 20  # rounds before the estimated height is used
    FIT_ITERATIONS = 10     # max. Gauss-Newton steps in _fit_with_height

    def __init__(self):
        super().__init__('uwb_node')
        self.declare_parameter('anchor_addresses', [1])
        self.declare_parameter('anchor_positions', [0.0, 0.0])
        self.declare_parameter('goal_frame', 'odom')
        self.declare_parameter('goal_topic', 'goal_update')
        self.declare_parameter('publish_period', 0.5)
        self._publish_period = float(self.get_parameter('publish_period').value)

        self.uwb_publisher = UwbPublisher(self,
                                          goal_frame=self.get_parameter('goal_frame').value,
                                          goal_topic=self.get_parameter('goal_topic').value)
        self._h2 = 0.0              # estimated (height of the tag above the anchors)^2, m^2
        self._height_rounds = 0
        self._kf_pos = None         # Kalman filter: estimated (x, y) in goal_frame, None = no point yet
        self._kf_var = 0.0          # its variance, m^2 (the same for x and y)
        self._kf_time = 0.0         # time of the last point, s (time.monotonic)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        anchors = list(self.get_parameter('anchor_addresses').value)
        if not anchors:
            self.get_logger().error('anchor_addresses is empty')
            return
        flat = list(self.get_parameter('anchor_positions').value)
        if len(flat) != 2 * len(anchors):
            self.get_logger().error('anchor_positions needs %d values (x, y per anchor), got %d'
                                    % (2 * len(anchors), len(flat)))
            return
        self.positions = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
        try:
            self.get_logger().info('initialising %d anchors at addresses %s' % (
                len(anchors), ', '.join('0x%04X' % a for a in anchors)))
            uwb_driver.init_dw3000(len(anchors))
            from uwb_package.driver.handshake import register_with_tag

            registered = [] # make sure the tag is running first, otherwise the anchors will never register
            for device, addr in enumerate(anchors):
                uwb_driver.select_device(device)
                self.get_logger().info('anchor 0x%04X: registering at the tag' % addr)
                tag_addr = None
                while tag_addr is None:
                    if self._stop.is_set():
                        return
                    tag_addr = register_with_tag(addr, max_tries=1)
                registered.append(addr)
                self.uwb_publisher.publish_anchors(registered)
                self.get_logger().info('anchor 0x%04X: registered at tag 0x%04X' % (addr, tag_addr))

            self.get_logger().info('ready: anchors %s registered at tag 0x%04X' % (
                ', '.join('0x%04X' % a for a in registered), tag_addr))

            self._handle_events(anchors)
        except Exception as e:
            self.get_logger().error('UWB failed: %s' % e)

    def _handle_events(self, anchors):
        """
        Listen on all anchors: turn every complete round of distances into a
        filtered position and publish it every publish_period, log text
        messages (e.g. the tag's "Hallo <address>" test, see
        driver/handshake.py), and every STATS_PERIOD the rate of the rounds
        and the slack of the responses.
        """
        from uwb_package.driver import commmunication_utils as cu
        from uwb_package.driver import ranging

        distances = [float('nan')] * len(anchors)
        t_publish = t_stats = time.monotonic()
        rounds = 0                                       # complete rounds since the last stats line
        while True:
            event = uwb_driver.receive_event(anchors, self._stop)
            if event is None:
                return
            now = time.monotonic()
            if now - t_stats >= self.STATS_PERIOD:
                # slack of the responses: how far POLL_RX_TO_RESP_TX_DLY_UUS could be lowered
                slack_min, sends, late = ranging.take_slack()
                self.get_logger().info(
                    '%.1f rounds/s, response slack min %s us of %.0f us (%d sends, %d late)' % (
                        rounds / (now - t_stats),
                        '-' if slack_min is None else '%.0f' % slack_min,
                        ranging.POLL_RX_TO_RESP_TX_DLY_UUS * 512 / 499.2, sends, late))
                t_stats, rounds = now, 0
            if event[0] == 'range':
                _, device, tag_addr, distance = event
                if distance is None:
                    self.get_logger().warning('anchor 0x%04X (DW3000 %d): ranging with tag 0x%04X failed'
                                              % (anchors[device], device, tag_addr))
                    continue
                distances[device] = distance
                # debug only (about 30 lines/s): --ros-args --log-level uwb_node:=debug
                self.get_logger().debug('anchor 0x%04X (DW3000 %d): distance to tag 0x%04X: %.2f m'
                                        % (anchors[device], device, tag_addr, distance))
                if device == len(anchors) - 1 and not any(math.isnan(d) for d in distances):
                    pos = self.get_coordinates(distances)
                    # into the fixed frame now, with the pose of the vehicle at this moment
                    fixed = self.uwb_publisher.to_goal_frame(pos) if pos is not None else None
                    if fixed is not None:
                        tag, vehicle = fixed
                        rounds += 1
                        goal = self.kalman(tag, now)                 # filter every round ...
                        if now - t_publish >= self._publish_period:  # ... send every publish_period
                            self.uwb_publisher.publish_goal(goal, vehicle)
                            t_publish = now
                    distances = [float('nan')] * len(anchors)        # start a new round
            else:
                _, device, (code, src, _, payload) = event
                if code == cu.MSG_TEXT:
                    self.get_logger().info('anchor 0x%04X (DW3000 %d) got from tag 0x%04X: "%s"' % (
                        anchors[device], device, src, payload.decode('utf-8', 'replace')))

    def destroy_node(self):
        self._stop.set()
        self._worker.join(timeout=2.0)
        uwb_driver.shutdown()
        super().destroy_node()

    def get_coordinates(self, distances):
        """
        distances: [d, ...] in m (3D, from the anchor to the tag) -> (x, y) of the
        tag relative to the vehicle, or None

        The tag is worn by a person and is higher than the anchors on the
        vehicle by an unknown h, so d^2 = horizontal distance^2 + h^2.
        All anchors are assumed to be at the same height.

        1. _trilaterate: x, y without knowing h (h^2 is the same in every d^2
           and cancels out). With 3 anchors this is exact for x, y and h, so
           all the noise of the distances ends up in x, y.
        2. h^2 is computed from this result and averaged over many rounds
           (the tag on a person hardly changes its height); nothing has to be
           measured or configured.
        3. _fit_with_height: with this h fixed there are 3 distances for only
           2 unknowns, the least squares fit averages out part of the noise.
        """
        pos = self._trilaterate(distances)
        if pos is None:
            return None
        h2 = sum(d * d - (pos[0] - xi) ** 2 - (pos[1] - yi) ** 2
                 for (xi, yi), d in zip(self.positions, distances)) / len(distances)
        # noise can make h2 negative; it is averaged as is (clipping each round
        # would bias the average upwards) and only clipped where it is used
        self._height_rounds += 1
        if self._height_rounds == 1:
            self._h2 = h2
        else:                      # running average, slowly follows changes
            alpha = max(1.0 / self._height_rounds, self.HEIGHT_ALPHA)
            self._h2 += alpha * (h2 - self._h2)
        if self._height_rounds % 50 == 0:
            self.get_logger().info('estimated height of the tag above the anchors: %.2f m'
                                   % math.sqrt(max(self._h2, 0.0)))
        if self._height_rounds < self.HEIGHT_MIN_ROUNDS:
            return pos             # height not known well enough yet
        return self._fit_with_height(pos, distances, max(self._h2, 0.0))

    def _fit_with_height(self, start, distances, h2):
        """
        Gauss-Newton: (x, y) that best fits all distances with the height
        difference h^2 fixed, starting at start -> (x, y)
        """
        x, y = start
        for _ in range(self.FIT_ITERATIONS):
            a11 = a12 = a22 = b1 = b2 = 0.0
            for (xi, yi), d in zip(self.positions, distances):
                rho = math.sqrt((x - xi) ** 2 + (y - yi) ** 2 + h2)
                if rho < 1e-6:
                    return start
                jx, jy = (x - xi) / rho, (y - yi) / rho  # derivative of rho
                r = d - rho                              # residual
                a11 += jx * jx; a12 += jx * jy; a22 += jy * jy
                b1 += jx * r;   b2 += jy * r
            det = a11 * a22 - a12 * a12
            if abs(det) < 1e-9:
                return start
            dx, dy = (a22 * b1 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det
            x, y = x + dx, y + dy
            if dx * dx + dy * dy < 1e-8:                 # converged (step < 0.1 mm)
                break
        return x, y

    def _trilaterate(self, distances):
        """distances: [d, ...] in m -> (x, y) or None, independent of the height of the tag"""
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
    
    def kalman(self, point, t):
        """
        Kalman filter over the positions in the fixed frame, runs on with
        every new point (a goal can go out after every round).
        Model: the tag stays where it is, but may move a little; the longer
        since the last point, the more (process noise KALMAN_Q per second).
        Each point is a measurement with noise KALMAN_R. x and y are filtered
        separately; with the same R and Q they share one variance.

        point: (x, y) just measured, t: its time in s -> filtered (x, y)
        """
        if self._kf_pos is None:          # start at the first measurement ...
            self._kf_pos, self._kf_var = point, self.KALMAN_R   # ... as uncertain as any
        else:
            dt = max(t - self._kf_time, 0.0)
            self._kf_var += self.KALMAN_Q * dt                  # predict: the tag may have moved
            gain = self._kf_var / (self._kf_var + self.KALMAN_R)
            self._kf_pos = (self._kf_pos[0] + gain * (point[0] - self._kf_pos[0]),   # update: move
                            self._kf_pos[1] + gain * (point[1] - self._kf_pos[1]))   # towards it
            self._kf_var *= 1 - gain
        self._kf_time = t
        return self._kf_pos


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

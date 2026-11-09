"""
ROS 2 node for the UWB anchors on the Raspberry Pi.

Each anchor is one DW3000 on the shared SPI bus: the i-th address in
anchor_addresses belongs to device i (the i-th CS pin in
driver/dw_platform/port.py). On start the node initialises these devices
and registers each anchor at the tag (handshake, see driver/handshake.py).
After that, as a test, it prints the text messages the tag sends to the
anchors. The DW3000 work runs in a worker thread, so the node keeps
spinning while it waits for the tag. Progress and result go out through
UwbPublisher.

Parameters:
  anchor_addresses  addresses of the anchors, one per DW3000, e.g. [1, 2, 3]
                    (default [1])
"""

import threading

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from uwb_package import uwb_driver
from uwb_package.uwb_publisher import UwbPublisher


class UwbNode(Node):

    def __init__(self):
        super().__init__('uwb_node')
        self.declare_parameter('anchor_addresses', [1])

        self.uwb_publisher = UwbPublisher(self)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        anchors = list(self.get_parameter('anchor_addresses').value)
        if not anchors:
            self.uwb_publisher.publish_status('error: parameter anchor_addresses is empty')
            return
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

            self._print_test_messages(anchors)
        except Exception as e:
            self.get_logger().error('UWB setup failed: %s' % e)
            self.uwb_publisher.publish_status('error: %s' % e)

    def _print_test_messages(self, anchors):
        """
        Test after the handshake: listen on all anchors and print every text
        message (the tag's "Hallo <address>", see driver/handshake.py). Each
        is addressed to one anchor, so only that anchor prints it.
        """
        from uwb_package.driver import commmunication_utils as cu

        while True:
            got = uwb_driver.receive_msg(anchors, self._stop)
            if got is None:
                return
            device, (code, src, dest, payload) = got
            if code == cu.MSG_TEXT:
                self.get_logger().info('anchor 0x%04X (DW3000 %d) got from tag 0x%04X: "%s"' % (
                    anchors[device], device, src, payload.decode('utf-8', 'replace')))

    def destroy_node(self):
        self._stop.set()
        self._worker.join(timeout=2.0)
        uwb_driver.shutdown()
        super().destroy_node()


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

"""
handshake.py

Registration of the anchors at the tag. Builds on commmunication_utils;
the DW3000 must be initialised and configured first, with the same
configuration as the other side.

    ANCHOR                                  TAG
    REGISTER (to BROADCAST) ------------>   stores the anchor's address
                            <------------   ACK (to the anchor)
    (no ACK in time: send REGISTER again)

The anchor does not know the tag's address yet, so REGISTER goes to
BROADCAST; the ACK carries the tag's address as its source, so after the
handshake both sides know each other.
"""

from . import utime as time

from . import commmunication_utils as cu


def register_with_tag(my_addr: int, ack_timeout_ms=200, retry_ms=500, max_tries=None):
    """
    Anchor side: send REGISTER until the tag answers with ACK.

    Returns the tag's address, or None after `max_tries` attempts without
    an ACK (None = keep trying forever).
    """
    tries = 0
    while max_tries is None or tries < max_tries:
        tries += 1
        cu.write_msg(cu.MSG_REGISTER, cu.BROADCAST, my_addr)

        t_start = time.ticks_ms()
        while True:
            remaining = ack_timeout_ms - time.ticks_diff(time.ticks_ms(), t_start)
            if remaining <= 0:
                break
            msg = cu.read_msg(timeout_ms=remaining, my_addr=my_addr)
            if msg is None:
                break
            code, src, dest, _ = msg
            if code == cu.MSG_ACK and dest == my_addr:
                return src

        time.sleep_ms(retry_ms)
    return None


def collect_anchors(my_addr: int, count: int, linger_ms=2000, on_register=None):
    """
    Tag side: wait until `count` different anchors have registered and
    acknowledge every REGISTER.

    Returns the anchors' addresses in the order they registered.
    `on_register(addr, is_new)` is called for every REGISTER received.

    After the last anchor has registered, REGISTERs are still answered for
    `linger_ms`: if an ACK got lost, that anchor sends REGISTER again and
    would otherwise never be acknowledged.
    """
    anchors = []
    t_done = None
    while True:
        timeout_ms = None
        if t_done is not None:
            timeout_ms = linger_ms - time.ticks_diff(time.ticks_ms(), t_done)
            if timeout_ms <= 0:
                return anchors

        msg = cu.read_msg(timeout_ms=timeout_ms, my_addr=my_addr)
        if msg is None:
            continue
        code, src, _, _ = msg
        if code != cu.MSG_REGISTER:
            continue

        cu.write_msg(cu.MSG_ACK, src, my_addr)
        is_new = src not in anchors
        if is_new:
            anchors.append(src)
        if on_register is not None:
            on_register(src, is_new)

        if t_done is None and len(anchors) >= count:
            t_done = time.ticks_ms()


# ---------------------------------------------------------------------------
# Test after the handshake: the tag sends "Hallo <address>" to each
# registered anchor. Each message is addressed to one anchor only, so only
# that anchor takes it (read_msg / parse_msg with my_addr); the others hear
# the frame but drop it.
# ---------------------------------------------------------------------------
def test_text(addr: int) -> str:
    """The test text for the anchor with address `addr`."""
    return "Hallo 0x%04X" % addr


def send_test_messages(my_addr: int, anchors):
    """Tag side: send test_text(addr) as MSG_TEXT to every anchor in `anchors`."""
    for addr in anchors:
        cu.write_msg(cu.MSG_TEXT, addr, my_addr, test_text(addr).encode())

"""
commmunication_utils.py

Sending and receiving messages with the DW3000. Builds on decadriver only;
the caller must have reset, initialised and configured the DW3000 first
(port.reset_dwic, dwt_initialise, dwt_configure), with the same
configuration as the other side.

Two layers:
  write_frame / read_frame   raw frame bytes; the DW IC appends and checks
                             the 2-byte FCS (CRC) itself
  rx_start / rx_poll         receiving without blocking (e.g. to listen on
                             several DW3000 at once)
  write_msg   / read_msg     IEEE 802.15.4 data frame with PAN ID, source
                             and destination address and a function code
  build_msg / parse_msg      such a message as frame bytes, and back

Message layout (write_msg / read_msg), all fields little-endian:
  0-1  frame control 0x8841 (data frame, PAN ID compression, short addresses)
  2    sequence number
  3-4  PAN ID
  5-6  destination address (BROADCAST = to everyone)
  7-8  source address
  9    function code (MSG_* below)
  10-  payload
"""

import utime as time

from decadriver import deca_device as dwt
from decadriver import deca_regs as R

# Function codes
MSG_REGISTER = 0x01     # anchor -> tag
MSG_ACK = 0x02          # tag -> anchor
MSG_POLL = 0x21         # tag -> anchor
MSG_RESP = 0x10         # anchor -> tag
MSG_FINAL = 0x23        # tag -> anchor
MSG_TEXT = 0x30         # text (UTF-8) in the payload, e.g. test messages

PAN_ID = 0xDECA
BROADCAST = 0xFFFF

FRAME_CTRL = 0x8841
MSG_HDR_LEN = 10        # MAC header (9 bytes) + function code

_seq = 0

def write_frame(data) -> bool:
    """
    Send `data` immediately and wait until it is out.
    Returns False if the DW IC refused to start the transmission.
    """
    dwt.dwt_writetxdata(len(data), bytes(data), 0)       # zero offset in TX buffer
    dwt.dwt_writetxfctrl(len(data) + R.FCS_LEN, 0, 0)    # zero offset, no ranging
    if dwt.dwt_starttx(R.DWT_START_TX_IMMEDIATE) != R.DWT_SUCCESS:
        return False
    while not (dwt.dwt_read32bitreg(R.SYS_STATUS_ID) & R.SYS_STATUS_TXFRS_BIT_MASK):
        pass
    dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_TXFRS_BIT_MASK)
    return True


def rx_start():
    """Turn the receiver on; then check with rx_poll() whether a frame came in."""
    dwt.dwt_rxenable(R.DWT_START_RX_IMMEDIATE)


def rx_poll():
    """
    Check the receiver started with rx_start(), without waiting.
    Returns None while it is still listening; otherwise the receiver is off
    again and the result is the frame's bytes (without the FCS), or b"" if
    a receive error occurred.
    """
    status = dwt.dwt_read32bitreg(R.SYS_STATUS_ID)
    if not status & (R.SYS_STATUS_RXFCG_BIT_MASK | R.SYS_STATUS_ALL_RX_ERR | R.SYS_STATUS_ALL_RX_TO):
        return None

    if not status & R.SYS_STATUS_RXFCG_BIT_MASK:
        dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_ALL_RX_ERR | R.SYS_STATUS_ALL_RX_TO)
        return b""

    frame_len = dwt.dwt_read32bitreg(R.RX_FINFO_ID) & R.RX_FINFO_RXFLEN_BIT_MASK
    data = dwt.dwt_readrxdata(frame_len - R.FCS_LEN, 0) if frame_len > R.FCS_LEN else b""
    dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_RXFCG_BIT_MASK)
    return data


def read_frame(timeout_ms=None):
    """
    Receive one frame. Returns its bytes (without the FCS), or None if a
    receive error occurred or nothing arrived within `timeout_ms`
    (None = wait forever).
    """
    rx_start()
    t_start = time.ticks_ms()

    while True:
        data = rx_poll()
        if data is not None:
            return data or None
        if timeout_ms is not None and time.ticks_diff(time.ticks_ms(), t_start) >= timeout_ms:
            dwt.dwt_forcetrxoff()
            dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_ALL_RX_GOOD |
                                  R.SYS_STATUS_ALL_RX_ERR | R.SYS_STATUS_ALL_RX_TO)
            return None


def build_msg(code: int, dest: int, src: int, payload=b"") -> bytearray:
    """
    Frame bytes of a message with function `code` from address `src` to
    address `dest` (BROADCAST = to everyone), for sending it yourself
    (e.g. delayed); write_msg() sends it right away.
    """
    global _seq
    frame = bytearray(MSG_HDR_LEN + len(payload))
    frame[0:2] = FRAME_CTRL.to_bytes(2, "little")
    frame[2] = _seq
    frame[3:5] = PAN_ID.to_bytes(2, "little")
    frame[5:7] = dest.to_bytes(2, "little")
    frame[7:9] = src.to_bytes(2, "little")
    frame[9] = code
    frame[MSG_HDR_LEN:] = payload
    _seq = (_seq + 1) & 0xFF
    return frame


def write_msg(code: int, dest: int, src: int, payload=b"") -> bool:
    """
    Send a message with function `code` from address `src` to address
    `dest` (BROADCAST = to everyone). Returns False if the transmission
    could not be started.
    """
    return write_frame(build_msg(code, dest, src, payload))


def parse_msg(data, my_addr=None):
    """
    Message from received frame bytes, as (code, src, dest, payload).
    Returns None if `data` is not a message of the format above, or if
    `my_addr` is given and the message is neither for it nor for BROADCAST.
    """
    if data is None or len(data) < MSG_HDR_LEN:
        return None
    if int.from_bytes(data[0:2], "little") != FRAME_CTRL:
        return None
    if int.from_bytes(data[3:5], "little") != PAN_ID:
        return None

    dest = int.from_bytes(data[5:7], "little")
    if my_addr is not None and dest not in (my_addr, BROADCAST):
        return None

    src = int.from_bytes(data[7:9], "little")
    return data[9], src, dest, bytes(data[MSG_HDR_LEN:])


def read_msg(timeout_ms=None, my_addr=None):
    """
    Receive the next message. With `my_addr`, only messages addressed to it
    or to BROADCAST are returned; other frames (and frames that are not
    messages of the format above) are skipped.

    Returns (code, src, dest, payload), or None if nothing matching arrived
    within `timeout_ms` (None = wait forever).
    """
    t_start = time.ticks_ms()
    while True:
        remaining = None
        if timeout_ms is not None:
            remaining = timeout_ms - time.ticks_diff(time.ticks_ms(), t_start)
            if remaining <= 0:
                return None

        msg = parse_msg(read_frame(remaining), my_addr)
        if msg is not None:
            return msg

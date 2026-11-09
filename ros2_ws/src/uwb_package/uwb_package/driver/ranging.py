"""
ranging.py

Distance between the tag and one anchor by double-sided two-way ranging
(DS-TWR), with the messages of commmunication_utils. Timing and time of
flight formula as in ex_05a / ex_05b; the DW3000 must be initialised and
configured first, with set_antenna_delays() called and the same
configuration as the other side.

    TAG                                     ANCHOR
    T1  POLL  (to the anchor) ---------->   T2
    T4  <----------------------- RESP       T3 = T2 + POLL_RX_TO_RESP_TX_DLY
    T5  FINAL (T1, T4, T5) ------------->   T6   -> anchor computes the distance

The tag only drives the exchange (range_anchor); the anchor gets the
distance (respond).
"""

from .decadriver import deca_device as dwt
from .decadriver import deca_regs as R
from .shared_data.shared_defines import UUS_TO_DWT_TIME, SPEED_OF_LIGHT
from .shared_data.shared_functions import (get_tx_timestamp_u64, get_rx_timestamp_u64,
                                           final_msg_get_ts, final_msg_set_ts)
from . import commmunication_utils as cu

# Default antenna delay values for 64 MHz PRF (calibrate per device).
TX_ANT_DLY = 16385
RX_ANT_DLY = 16385

# --- timing (uus; 1 uus = 512/499.2 us ~ 1.0256 us), as in ex_05a/ex_05b ----
# Anchor: poll RX -> response TX. Tag: response RX -> final TX. Both must be
# longer than the host's turnaround (MicroPython on the tag needs the most).
POLL_RX_TO_RESP_TX_DLY_UUS = 15000
RESP_RX_TO_FINAL_TX_DLY_UUS = 15000
# Slack each side of an expected frame.
WINDOW_MARGIN_UUS = 1000
# Tag: end of poll TX -> receiver on, and how long it stays on for the response.
POLL_TX_TO_RESP_RX_DLY_UUS = POLL_RX_TO_RESP_TX_DLY_UUS - 200 - WINDOW_MARGIN_UUS
RESP_RX_TIMEOUT_UUS = 300 + 2 * WINDOW_MARGIN_UUS
# Anchor: end of response TX -> receiver on, and how long it stays on for the final.
RESP_TX_TO_FINAL_RX_DLY_UUS = RESP_RX_TO_FINAL_TX_DLY_UUS - 200 - WINDOW_MARGIN_UUS
FINAL_RX_TIMEOUT_UUS = 220 + 2 * WINDOW_MARGIN_UUS

# Final payload: poll TX, response RX and final TX timestamp of the tag
# (low 32 bits each, LSB first).
FINAL_POLL_TX_TS_IDX = 0
FINAL_RESP_RX_TS_IDX = 4
FINAL_FINAL_TX_TS_IDX = 8
FINAL_PAYLOAD_LEN = 12


def set_antenna_delays():
    dwt.dwt_setrxantennadelay(RX_ANT_DLY)
    dwt.dwt_settxantennadelay(TX_ANT_DLY)


def _send(frame, mode):
    """Load `frame` (ranging bit set) and start TX. False if the DW IC refused."""
    dwt.dwt_writetxdata(len(frame), bytes(frame), 0)
    dwt.dwt_writetxfctrl(len(frame) + R.FCS_LEN, 0, 1)
    return dwt.dwt_starttx(mode) == R.DWT_SUCCESS


def _wait_frame():
    """Wait for the receiver turned on after TX (DWT_RESPONSE_EXPECTED)."""
    while True:
        data = cu.rx_poll()
        if data is not None:
            dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_TXFRS_BIT_MASK)
            return data


def range_anchor(my_addr: int, anchor_addr: int) -> bool:
    """
    Tag side: one DS-TWR exchange with the anchor `anchor_addr`.
    Returns True if the final went out (the anchor then has the distance),
    False if the anchor did not answer or the final was too late.
    """
    dwt.dwt_setrxaftertxdelay(POLL_TX_TO_RESP_RX_DLY_UUS)
    dwt.dwt_setrxtimeout(RESP_RX_TIMEOUT_UUS)
    try:
        poll = cu.build_msg(cu.MSG_POLL, anchor_addr, my_addr)
        if not _send(poll, R.DWT_START_TX_IMMEDIATE | R.DWT_RESPONSE_EXPECTED):
            return False

        msg = cu.parse_msg(_wait_frame(), my_addr)
        if msg is None or msg[0] != cu.MSG_RESP or msg[1] != anchor_addr:
            return False

        poll_tx_ts = get_tx_timestamp_u64()
        resp_rx_ts = get_rx_timestamp_u64()

        # Final TX time: DX_TIME takes the high 32 bits of the 40-bit time.
        final_tx_time = ((resp_rx_ts + RESP_RX_TO_FINAL_TX_DLY_UUS * UUS_TO_DWT_TIME) >> 8) & 0xFFFFFFFF
        dwt.dwt_setdelayedtrxtime(final_tx_time)
        # Final TX timestamp = programmed time (bit 0 ignored by the chip)
        # plus the TX antenna delay.
        final_tx_ts = ((final_tx_time & 0xFFFFFFFE) << 8) + TX_ANT_DLY

        final = cu.build_msg(cu.MSG_FINAL, anchor_addr, my_addr, bytes(FINAL_PAYLOAD_LEN))
        final_msg_set_ts(final, cu.MSG_HDR_LEN + FINAL_POLL_TX_TS_IDX, poll_tx_ts)
        final_msg_set_ts(final, cu.MSG_HDR_LEN + FINAL_RESP_RX_TS_IDX, resp_rx_ts)
        final_msg_set_ts(final, cu.MSG_HDR_LEN + FINAL_FINAL_TX_TS_IDX, final_tx_ts)
        if not _send(final, R.DWT_START_TX_DELAYED):
            return False

        while not (dwt.dwt_read32bitreg(R.SYS_STATUS_ID) & R.SYS_STATUS_TXFRS_BIT_MASK):
            pass
        dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_TXFRS_BIT_MASK)
        return True
    finally:
        dwt.dwt_setrxtimeout(0)


def respond(my_addr: int, tag_addr: int):
    """
    Anchor side: call right after a POLL from `tag_addr` to `my_addr` has
    been received (its RX timestamp is still in the DW3000). Sends the
    response, receives the final and computes the distance.
    Returns the distance in metres, or None if the exchange failed.
    """
    poll_rx_ts = get_rx_timestamp_u64()

    # Response TX time (high 32 bits of the 40-bit time).
    resp_tx_time = ((poll_rx_ts + POLL_RX_TO_RESP_TX_DLY_UUS * UUS_TO_DWT_TIME) >> 8) & 0xFFFFFFFF
    dwt.dwt_setdelayedtrxtime(resp_tx_time)
    dwt.dwt_setrxaftertxdelay(RESP_TX_TO_FINAL_RX_DLY_UUS)
    dwt.dwt_setrxtimeout(FINAL_RX_TIMEOUT_UUS)
    try:
        resp = cu.build_msg(cu.MSG_RESP, tag_addr, my_addr)
        if not _send(resp, R.DWT_START_TX_DELAYED | R.DWT_RESPONSE_EXPECTED):
            return None     # delayed TX time already passed

        msg = cu.parse_msg(_wait_frame(), my_addr)
        if (msg is None or msg[0] != cu.MSG_FINAL or msg[1] != tag_addr
                or len(msg[3]) < FINAL_PAYLOAD_LEN):
            return None

        resp_tx_ts = get_tx_timestamp_u64()
        final_rx_ts = get_rx_timestamp_u64()
        payload = msg[3]
        poll_tx_ts = final_msg_get_ts(payload, FINAL_POLL_TX_TS_IDX)
        resp_rx_ts = final_msg_get_ts(payload, FINAL_RESP_RX_TS_IDX)
        final_tx_ts = final_msg_get_ts(payload, FINAL_FINAL_TX_TS_IDX)

        # Time of flight. The 32-bit counters wrap, so all differences are
        # taken modulo 2^32 (they are positive and below 2^32 ticks, ~67 ms).
        Ra = (resp_rx_ts - poll_tx_ts) & 0xFFFFFFFF
        Rb = (final_rx_ts - resp_tx_ts) & 0xFFFFFFFF
        Da = (final_tx_ts - resp_rx_ts) & 0xFFFFFFFF
        Db = (resp_tx_ts - poll_rx_ts) & 0xFFFFFFFF
        # tof = (Ra*Rb - Da*Db) / (Ra + Rb + Da + Db), exact integer
        # numerator/denominator, truncated to whole device ticks as upstream.
        tof_dtu = int((Ra * Rb - Da * Db) / (Ra + Rb + Da + Db))
        return tof_dtu * R.DWT_TIME_UNITS * SPEED_OF_LIGHT
    finally:
        dwt.dwt_setrxtimeout(0)

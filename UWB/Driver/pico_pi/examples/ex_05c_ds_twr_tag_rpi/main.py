"""
examples/ex_05c_ds_twr_tag_rpi/main.py

Double-sided two-way ranging, TAG (initiator) side, talking to the Rust
anchor on the Raspberry Pi:
    raspberry_pi/example_raspberry/src/bin/double_sided_rtt_responder.rs
Not an upstream example -- it speaks the Rust example's protocol, not the
one of ex_05a/ex_05b, so it does NOT work with ex_05b.

Exchange (T1..T6 as named in the Rust code):

    TAG (this)                         ANCHOR (Raspberry Pi)
    T1  poll  ------------------------>  T2
    T4  <------------------------ resp   T3 = T2 + 5 ms
    T5  final (T1, T4, T5) ----------->  T6   -> anchor prints the distance

Protocol details the Rust side expects:
  * Radio config = Rust Config::default(): channel 5, code 9 (PRF 64 MHz),
    6.8 Mbit/s, preamble 128, standard PHR, SFD type 0 (IEEE 8 symbol).
    ex_05a/ex_06a use SFD type 1, which the Rust side cannot receive.
  * Every frame must be a valid IEEE 802.15.4 MAC frame (the Rust side parses
    it with the ieee802154 crate). The anchor does not look at the poll's
    content or at any addresses.
  * The final's MAC payload is T1, T4, T5, each 5 bytes, MOST significant
    byte first (full 40-bit timestamps, unlike the 4-byte little-endian
    fields of the upstream examples).
  * The anchor sends its response 5 ms (5000 * 63898 ticks) after the poll
    RX, so the receive window below is centred on that. The anchor waits for
    the final without a timeout, so the tag can take as long as it needs
    (RESP_RX_TO_FINAL_TX_DLY_UUS) -- DS-TWR is insensitive to reply times.

Only one anchor may run at a time: the Rust responder answers every poll, so
several anchors would answer at the same moment and collide.
"""

import utime as time

from platform.port import port
from decadriver import deca_device as dwt
from decadriver import deca_regs as R
from decadriver.deca_types import DwtConfig
from config_options import txconfig_options
from shared_data.shared_defines import FRAME_LEN_MAX_EX, UUS_TO_DWT_TIME
from shared_data.shared_functions import get_tx_timestamp_u64, get_rx_timestamp_u64

APP_NAME = "DS TWR TAG -> RPi anchor (MicroPython) v0.1"

# Must match the Rust Config::default() (see module docstring).
config = DwtConfig(
    chan=5,
    txPreambLength=R.DWT_PLEN_128,
    rxPAC=R.DWT_PAC8,
    txCode=9,
    rxCode=9,
    sfdType=0,                 # IEEE 8 symbol SFD (Rust SfdSequence::IeeeShort)
    dataRate=R.DWT_BR_6M8,
    phrMode=R.DWT_PHRMODE_STD,
    phrRate=R.DWT_PHRRATE_STD,
    sfdTO=(129 + 8 - 8),
    stsMode=R.DWT_STS_MODE_OFF,
    stsLength=R.DWT_STS_LEN_64,
    pdoaMode=R.DWT_PDOA_M0,
)

# Inter-ranging delay period, in milliseconds.
RNG_DELAY_MS = 1000

# Default antenna delay values for 64 MHz PRF (calibrate per device).
TX_ANT_DLY = 16385
RX_ANT_DLY = 16385

# IEEE 802.15.4 data frames, 9-byte MAC header:
#   0-1 frame control (0x8841: data, PAN ID compression, short addresses),
#   2 sequence number, 3-4 PAN ID (0xDECA), 5-6 destination (0xFFFF =
#   broadcast), 7-8 source ("TG"), then the MAC payload.
# The DW IC appends the 2-byte checksum.
MAC_HDR = bytes([0x41, 0x88, 0, 0xCA, 0xDE, 0xFF, 0xFF, ord('T'), ord('G')])
MAC_HDR_LEN = len(MAC_HDR)
ALL_MSG_SN_IDX = 2
tx_poll_msg = bytearray(MAC_HDR + bytes([0x21]))           # payload content is ignored by the anchor
tx_final_msg = bytearray(MAC_HDR + bytes(3 * 5))           # payload: T1, T4, T5 (5 bytes each, big-endian)
FINAL_MSG_T1_IDX = MAC_HDR_LEN
FINAL_MSG_T4_IDX = MAC_HDR_LEN + 5
FINAL_MSG_T5_IDX = MAC_HDR_LEN + 10
FCS_LEN = R.FCS_LEN
RX_BUF_LEN = 32

TS_MASK = 0xFFFFFFFFFF      # 40-bit device time

# --- timing (uus; 1 uus = 512/499.2 us ~ 1.0256 us) ------------------------
# The anchor's poll RX -> response TX delay: 5000 us in the Rust code.
ANCHOR_REPLY_DLY_UUS = 5000 * 4992 // 5120     # = 4875 uus
# Slack each side of the expected response.
WINDOW_MARGIN_UUS = 1000
# End of poll TX -> receiver on.
POLL_TX_TO_RESP_RX_DLY_UUS = ANCHOR_REPLY_DLY_UUS - 200 - WINDOW_MARGIN_UUS
# How long the receiver stays on for the response.
RESP_RX_TIMEOUT_UUS = 300 + 2 * WINDOW_MARGIN_UUS
# Response RX -> final TX. Must be longer than this side's host turnaround.
RESP_RX_TO_FINAL_TX_DLY_UUS = 15000
# Preamble detect timeout, in PACs. 0 = off.
PRE_TIMEOUT = 0


def final_msg_set_ts_be(buf, offset: int, ts: int):
    """Write a 40-bit timestamp as 5 bytes, most significant byte first."""
    buf[offset:offset + 5] = (ts & TS_MASK).to_bytes(5, "big")


def main():
    print(APP_NAME)

    port.spi_set_rate_high()
    port.reset_dwic()
    time.sleep_ms(2)  # INIT_RC -> IDLE_RC

    while not dwt.dwt_checkidlerc():
        pass

    if dwt.dwt_initialise(R.DWT_DW_INIT) == R.DWT_ERROR:
        print("INIT FAILED")
        while True:
            pass

    if dwt.dwt_configure(config):
        print("CONFIG FAILED")
        while True:
            pass

    dwt.dwt_configuretxrf(txconfig_options)

    dwt.dwt_setrxantennadelay(RX_ANT_DLY)
    dwt.dwt_settxantennadelay(TX_ANT_DLY)

    # Expected response's delay and timeout (one response, always the same).
    dwt.dwt_setrxaftertxdelay(POLL_TX_TO_RESP_RX_DLY_UUS)
    dwt.dwt_setrxtimeout(RESP_RX_TIMEOUT_UUS)
    dwt.dwt_setpreambledetecttimeout(PRE_TIMEOUT)

    dwt.dwt_setleds(R.DWT_LEDS_ENABLE | R.DWT_LEDS_INIT_BLINK)

    print("Tag ready (rx on after %d uus, timeout %d uus, final after %d uus)" %
          (POLL_TX_TO_RESP_RX_DLY_UUS, RESP_RX_TIMEOUT_UUS, RESP_RX_TO_FINAL_TX_DLY_UUS))

    frame_seq_nb = 0
    try:
        while True:
            # Write the poll and prepare transmission.
            tx_poll_msg[ALL_MSG_SN_IDX] = frame_seq_nb
            dwt.dwt_writetxdata(len(tx_poll_msg), tx_poll_msg, 0)       # zero offset in TX buffer
            dwt.dwt_writetxfctrl(len(tx_poll_msg) + FCS_LEN, 0, 1)      # zero offset, ranging

            # Start transmission; reception is enabled automatically after the
            # frame is sent and the delay set by dwt_setrxaftertxdelay elapses.
            dwt.dwt_starttx(R.DWT_START_TX_IMMEDIATE | R.DWT_RESPONSE_EXPECTED)

            # Poll for reception of a frame or error/timeout.
            while True:
                status_reg = dwt.dwt_read32bitreg(R.SYS_STATUS_ID)
                if status_reg & (R.SYS_STATUS_RXFCG_BIT_MASK |
                                 R.SYS_STATUS_ALL_RX_TO |
                                 R.SYS_STATUS_ALL_RX_ERR):
                    break

            frame_seq_nb = (frame_seq_nb + 1) & 0xFF

            if status_reg & R.SYS_STATUS_RXFCG_BIT_MASK:
                t_rx = time.ticks_us()

                # Clear good RX frame event and TX frame sent.
                dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_RXFCG_BIT_MASK | R.SYS_STATUS_TXFRS_BIT_MASK)

                frame_len = dwt.dwt_read32bitreg(R.RX_FINFO_ID) & FRAME_LEN_MAX_EX
                rx_buffer = dwt.dwt_readrxdata(min(frame_len, RX_BUF_LEN), 0)

                # The anchor's response is a data frame (frame type = 1); its
                # payload carries nothing we need.
                if frame_len >= 3 and (rx_buffer[0] & 0x07) == 0x01:
                    t1 = get_tx_timestamp_u64()     # poll TX
                    t4 = get_rx_timestamp_u64()     # response RX

                    # Final message transmission time: DX_TIME takes the high 32
                    # bits of the 40-bit time (shift by 8, keep 32 bits).
                    final_tx_time = ((t4 + RESP_RX_TO_FINAL_TX_DLY_UUS * UUS_TO_DWT_TIME) >> 8) & 0xFFFFFFFF
                    dwt.dwt_setdelayedtrxtime(final_tx_time)

                    # Final TX timestamp = programmed time (bit 0 ignored by the
                    # chip) plus the TX antenna delay.
                    t5 = (((final_tx_time & 0xFFFFFFFE) << 8) + TX_ANT_DLY) & TS_MASK

                    final_msg_set_ts_be(tx_final_msg, FINAL_MSG_T1_IDX, t1)
                    final_msg_set_ts_be(tx_final_msg, FINAL_MSG_T4_IDX, t4)
                    final_msg_set_ts_be(tx_final_msg, FINAL_MSG_T5_IDX, t5)

                    # Write and send the final message.
                    tx_final_msg[ALL_MSG_SN_IDX] = frame_seq_nb
                    dwt.dwt_writetxdata(len(tx_final_msg), tx_final_msg, 0)
                    dwt.dwt_writetxfctrl(len(tx_final_msg) + FCS_LEN, 0, 1)

                    # If dwt_starttx() fails (the delayed time had already
                    # passed), abandon this exchange.
                    ret = dwt.dwt_starttx(R.DWT_START_TX_DELAYED)
                    t_queued = time.ticks_us()
                    if ret == R.DWT_SUCCESS:
                        while not (dwt.dwt_read32bitreg(R.SYS_STATUS_ID) & R.SYS_STATUS_TXFRS_BIT_MASK):
                            pass
                        dwt.dwt_write32bitreg(R.SYS_STATUS_ID, R.SYS_STATUS_TXFRS_BIT_MASK)
                        frame_seq_nb = (frame_seq_nb + 1) & 0xFF
                        print("final sent (host turnaround %d us); distance is shown by the anchor" %
                              time.ticks_diff(t_queued, t_rx))
                    else:
                        print("TOO LATE: host took %d us; raise RESP_RX_TO_FINAL_TX_DLY_UUS" %
                              time.ticks_diff(t_queued, t_rx))
                else:
                    print("unexpected frame, len", frame_len)
            else:
                # Clear RX error/timeout events.
                dwt.dwt_write32bitreg(R.SYS_STATUS_ID,
                                      R.SYS_STATUS_ALL_RX_TO | R.SYS_STATUS_ALL_RX_ERR | R.SYS_STATUS_TXFRS_BIT_MASK)
                print("no response from anchor, status 0x%08X" %
                      (status_reg & (R.SYS_STATUS_ALL_RX_TO | R.SYS_STATUS_ALL_RX_ERR)))

            # Delay between ranging exchanges.
            time.sleep_ms(RNG_DELAY_MS)
    except KeyboardInterrupt:
        dwt.dwt_forcetrxoff()
        print("\nStopped by user (Ctrl-C). Transceiver forced off.")


if __name__ == "__main__":
    main()

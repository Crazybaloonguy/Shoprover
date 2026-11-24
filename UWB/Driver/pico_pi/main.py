"""
main.py

Tag: first the handshake (see handshake.py): waits until ANCHOR_COUNT
anchors have registered, acknowledges each of them and stores their
addresses in `anchors`. Start this first, then the anchors.

Then the ranging (see ranging.py): one DS-TWR exchange with each anchor in
turn, ANCHOR_GAP_MS apart, so every anchor gets its current distance to
the tag; this round repeats every RANGING_INTERVAL_MS (or right away, if it
took longer). Every STATS_INTERVAL_MS a summary is printed: rounds, failed
exchanges and the smallest slack of the final (see ranging.take_slack).
"""

import utime as time

from dw_platform.port import port
from decadriver import deca_device as dwt
from decadriver import deca_regs as R
from decadriver.deca_types import DwtConfig
from config_options import txconfig_options
from handshake import collect_anchors
from ranging import range_anchor, set_antenna_delays, take_slack, RESP_RX_TO_FINAL_TX_DLY_UUS

APP_NAME = "HANDSHAKE TAG (MicroPython) v0.1"

# Must match the anchors.
config = DwtConfig(
    chan=5,
    txPreambLength=R.DWT_PLEN_128,
    rxPAC=R.DWT_PAC8,
    txCode=9,
    rxCode=9,
    sfdType=1,                 # non-standard 8 symbol SFD
    dataRate=R.DWT_BR_6M8,
    phrMode=R.DWT_PHRMODE_STD,
    phrRate=R.DWT_PHRRATE_STD,
    sfdTO=(129 + 8 - 8),
    stsMode=R.DWT_STS_MODE_OFF,
    stsLength=R.DWT_STS_LEN_64,
    pdoaMode=R.DWT_PDOA_M0,
)

TAG_ADDR = 0x0100
ANCHOR_COUNT = 3

# Ranging: pause between two anchors, and from round start to round start
# (50 ms = 20 rounds/s; a round takes ~100 ms as long as the delays in
# ranging.py are 15 ms, then the next one starts right away).
ANCHOR_GAP_MS = 1
RANGING_INTERVAL_MS = 50
STATS_INTERVAL_MS = 1000    # summary on the console


def on_register(addr, is_new):
    if is_new:
        print("anchor 0x%04X registered" % addr)
    else:
        print("anchor 0x%04X registered again (ACK lost?), ACK repeated" % addr)


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
    set_antenna_delays()
    dwt.dwt_setleds(R.DWT_LEDS_ENABLE | R.DWT_LEDS_INIT_BLINK)

    print("Tag 0x%04X waiting for %d anchors" % (TAG_ADDR, ANCHOR_COUNT))
    try:
        anchors = collect_anchors(TAG_ADDR, ANCHOR_COUNT, on_register=on_register)
        print("Handshake done, anchors:", ", ".join("0x%04X" % a for a in anchors))

        print("Ranging every %d ms, %d ms between anchors (Ctrl-C to stop)"
              % (RANGING_INTERVAL_MS, ANCHOR_GAP_MS))
        rounds, failed = 0, {}
        t_stats = time.ticks_ms()
        while True:
            t_round = time.ticks_ms()
            for i, addr in enumerate(anchors):
                if i > 0:
                    time.sleep_ms(ANCHOR_GAP_MS)
                if not range_anchor(TAG_ADDR, addr):
                    failed[addr] = failed.get(addr, 0) + 1
            rounds += 1

            # Summary instead of one line per round (20 lines/s would slow the tag down).
            if time.ticks_diff(time.ticks_ms(), t_stats) >= STATS_INTERVAL_MS:
                slack_min, sends, late = take_slack()
                print("%d rounds/%d ms, failed: %s, final slack min %s us of %.0f us (%d sends, %d late)" % (
                    rounds, time.ticks_diff(time.ticks_ms(), t_stats),
                    ", ".join("0x%04X: %d" % a for a in failed.items()) or "none",
                    "-" if slack_min is None else "%.0f" % slack_min,
                    RESP_RX_TO_FINAL_TX_DLY_UUS * 512 / 499.2, sends, late))
                rounds, failed = 0, {}
                t_stats = time.ticks_ms()

            # Wait for the rest of the interval.
            rest = RANGING_INTERVAL_MS - time.ticks_diff(time.ticks_ms(), t_round)
            if rest > 0:
                time.sleep_ms(rest)
    except KeyboardInterrupt:
        dwt.dwt_forcetrxoff()
        print("\nStopped by user (Ctrl-C). Transceiver forced off.")


if __name__ == "__main__":
    main()

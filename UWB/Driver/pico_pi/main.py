"""
main.py

Tag side of the handshake (see handshake.py): waits until ANCHOR_COUNT
anchors have registered, acknowledges each of them and stores their
addresses in `anchors`, so later messages (e.g. ranging polls) can be
sent to them. Start this first, then the anchors.

As a test, it then sends "Hallo <address>" to every anchor once per
TEST_INTERVAL_MS, each message addressed to that anchor only.
"""

import utime as time

from dw_platform.port import port
from decadriver import deca_device as dwt
from decadriver import deca_regs as R
from decadriver.deca_types import DwtConfig
from config_options import txconfig_options
from handshake import collect_anchors, send_test_messages, test_text

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

# Test after the handshake: "Hallo <address>" to every anchor, this often.
TEST_INTERVAL_MS = 1000


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
    dwt.dwt_setleds(R.DWT_LEDS_ENABLE | R.DWT_LEDS_INIT_BLINK)

    print("Tag 0x%04X waiting for %d anchors" % (TAG_ADDR, ANCHOR_COUNT))
    try:
        anchors = collect_anchors(TAG_ADDR, ANCHOR_COUNT, on_register=on_register)
        print("Handshake done, anchors:", ", ".join("0x%04X" % a for a in anchors))

        print("Sending test messages every %d ms (Ctrl-C to stop)" % TEST_INTERVAL_MS)
        while True:
            send_test_messages(TAG_ADDR, anchors)
            print("sent:", ", ".join("'%s'" % test_text(a) for a in anchors))
            time.sleep_ms(TEST_INTERVAL_MS)
    except KeyboardInterrupt:
        dwt.dwt_forcetrxoff()
        print("\nStopped by user (Ctrl-C). Transceiver forced off.")


if __name__ == "__main__":
    main()

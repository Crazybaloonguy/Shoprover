"""
examples/util_toggle_rstn/main.py

Small hardware check: drives the DW3000's RSTn pin low and high in turn,
2 s each, so it can be followed with a multimeter / scope / LED.

Standalone on purpose (does not import platform.port, so no SPI setup).
RST_GPIO must match PINS["rst"] in platform/port.py:
  Flexypin = GP9, ArduPico = GP7.
"""

import time
from machine import Pin

RST_GPIO = 7
DELAY_S = 2


def main():
    rst = Pin(RST_GPIO, Pin.OUT, value=1)
    print("Toggling RSTn on GP%d every %d s (Ctrl+C to stop)" % (RST_GPIO, DELAY_S))
    try:
        while True:
            rst.value(0)
            print("RSTn = 0")
            time.sleep(DELAY_S)
            rst.value(1)
            print("RSTn = 1")
            time.sleep(DELAY_S)
    except KeyboardInterrupt:
        # Release the line again, as port.py does (pulled high externally)
        Pin(RST_GPIO, Pin.IN)
        print("Stopped, RSTn released")


main()

"""
examples/util_pin_test/main.py

GPIO / jumper-wire continuity test for the Raspberry Pi Pico 2 W.
MicroPython twin of tools/pin_test/pin_test/pin_test.ino, so it can be run
from Thonny without leaving the MicroPython firmware.

Every GPIO that reaches the 40-pin header is set to input with pull-up.
Touch a pin (or the far end of a wire plugged into it) to GND and a message
is printed; releasing it prints another one. The on-board LED is lit while
any pin is held at GND. Stop with Ctrl-C (or Thonny's Stop button).

Not tested: GPIO23/24/25/29 are wired to the CYW43439 wireless chip and the
VSYS sense divider on the Pico 2 W (datasheet section 2.1) and are not on
the header.

Pins marked "DWM3000 ..." are the signals the driver uses with
platform/port.py BOARD = "flexypin" (see docs/pinout.md). Wiring the
DWM3000EVB to those GPIOs lets the driver run without pin changes.

Needs nothing else from this project: open it in Thonny and press Run, or
save it to the Pico as main.py to run it on power-up.
"""

import utime as time
from machine import Pin

APP_NAME = "PIN TEST Pico 2 W (MicroPython) v0.1"

# (GPIO, physical header pin, DWM3000EVB signal or None)
PINS = (
    (0, 1, None),
    (1, 2, None),
    (2, 4, "IRQ (D8)"),
    (3, 5, "WAKEUP (D9)"),
    (4, 6, None),
    (5, 7, None),
    (6, 9, None),
    (7, 10, None),
    (8, 11, None),
    (9, 12, "RSTn (D7)"),
    (10, 14, None),
    (11, 15, None),
    (12, 16, None),
    (13, 17, None),
    (14, 19, None),
    (15, 20, None),
    (16, 21, "SPI MISO (D12)"),
    (17, 22, "SPI CSn (D10)"),
    (18, 24, "SPI CLK (D13)"),
    (19, 25, "SPI MOSI (D11)"),
    (20, 26, None),
    (21, 27, None),
    (22, 29, None),
    (26, 31, None),
    (27, 32, None),
    (28, 34, None),
)

# A pin must read the same level this long before a change is reported, so a
# wire scraping across a GND pad prints one message, not dozens.
DEBOUNCE_MS = 20


def pin_label(gpio, header, role):
    label = "GP%-2d (Pin %2d" % (gpio, header)
    if role:
        label += ", DWM3000 " + role
    return label + ")"


def main():
    print(APP_NAME)

    led = Pin("LED", Pin.OUT)
    pins = [Pin(gpio, Pin.IN, Pin.PULL_UP) for gpio, _, _ in PINS]
    labels = [pin_label(*p) for p in PINS]

    print("%d Pins mit Pull-Up aktiv. Pin mit GND verbinden -> Meldung." % len(pins))
    for label in labels:
        print("  " + label)
    print("Pins, die sofort gemeldet werden, lagen schon beim Start auf GND")
    print("(Kurzschluss oder angeschlossene Hardware zieht sie runter).")
    print()

    n = len(pins)
    reported_low = [False] * n  # last level that was printed
    raw_low = [False] * n       # last level read
    raw_since = [0] * n         # ticks_ms() when raw_low last changed
    start = time.ticks_ms()

    try:
        while True:
            now = time.ticks_ms()
            any_low = False

            for i in range(n):
                low = pins[i].value() == 0

                if low != raw_low[i]:
                    raw_low[i] = low
                    raw_since[i] = now
                elif low != reported_low[i] and time.ticks_diff(now, raw_since[i]) >= DEBOUNCE_MS:
                    reported_low[i] = low
                    print("[%8d ms] %s  -> %s" % (
                        time.ticks_diff(now, start),
                        labels[i],
                        "mit GND verbunden" if low else "wieder offen",
                    ))

                any_low = any_low or reported_low[i]

            led.value(any_low)
            time.sleep_ms(1)
    except KeyboardInterrupt:
        print("stopped")
    finally:
        led.value(0)


if __name__ == "__main__":
    main()

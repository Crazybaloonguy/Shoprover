"""
examples/util_pin_test/main.py

GPIO / jumper-wire continuity test for the Raspberry Pi 4. Twin of the Pico
version (and of tools/pin_test/pin_test/pin_test.ino).

Every GPIO on the 40-pin header is set to input with pull-up. Touch a pin
(or the far end of a wire plugged into it) to GND and a message is printed;
releasing it prints another one. Stop with Ctrl-C.

Run with the DWM3000EVB unplugged: python3 examples/util_pin_test/main.py

Notes for the Pi:
  - GPIO0/1 (ID EEPROM) are not tested.
  - GPIO2/3 have 1.8 kOhm pull-ups on the board, so they work as usual.
  - Pins the kernel has claimed (with SPI enabled: CE0/CE1 = GPIO8/7) are
    reported as "belegt" and skipped.
  - Testing switches pins that are in an alternate function (SPI, UART,
    I2C) to plain inputs. Their previous mode is read with `pinctrl get`
    before the test and restored with `pinctrl set` afterwards; if pinctrl
    is missing, reboot the Pi after the test.

Pins marked "DWM3000 ..." are the signals the driver uses (see
dw_platform/port.py).

Needs only python3-lgpio, nothing else from this project.
"""

import shutil
import subprocess
import time

import lgpio

APP_NAME = "PIN TEST Raspberry Pi 4 v0.1"

GPIOCHIP = 0

# (GPIO, physical header pin, DWM3000EVB signal or None)
PINS = (
    (2, 3, None),
    (3, 5, None),
    (4, 7, None),
    (5, 29, None),
    (6, 31, None),
    (7, 26, None),
    (8, 24, "SPI CSn (D10)"),
    (9, 21, "SPI MISO (D12)"),
    (10, 19, "SPI MOSI (D11)"),
    (11, 23, "SPI CLK (D13)"),
    (12, 32, None),
    (13, 33, None),
    (14, 8, None),
    (15, 10, None),
    (16, 36, None),
    (17, 11, None),
    (18, 12, None),
    (19, 35, None),
    (20, 38, None),
    (21, 40, None),
    (22, 15, None),
    (23, 16, "WAKEUP (D9)"),
    (24, 18, "IRQ (D8)"),
    (25, 22, "RSTn (D7)"),
    (26, 37, None),
    (27, 13, None),
)

# A pin must read the same level this long before a change is reported, so a
# wire scraping across a GND pad prints one message, not dozens.
DEBOUNCE_MS = 20


def pin_label(gpio, header, role):
    label = "GPIO%-2d (Pin %2d" % (gpio, header)
    if role:
        label += ", DWM3000 " + role
    return label + ")"


def pinctrl_save(gpio):
    """Return the `pinctrl set` arguments that restore this pin, or None."""
    try:
        out = subprocess.run(["pinctrl", "get", str(gpio)], capture_output=True,
                             text=True, check=True).stdout
        # e.g. " 9: a0    pd | lo // GPIO9 = SPI0_MISO"
        func, pull = out.split()[1:3]
        return [func, pull]
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def pinctrl_restore(saved):
    for gpio, args in saved.items():
        if args is not None:
            subprocess.run(["pinctrl", "set", str(gpio)] + args, check=False)


def main():
    print(APP_NAME)

    have_pinctrl = shutil.which("pinctrl") is not None
    saved = {}

    h = lgpio.gpiochip_open(GPIOCHIP)
    gpios, labels = [], []
    for gpio, header, role in PINS:
        label = pin_label(gpio, header, role)
        if have_pinctrl:
            saved[gpio] = pinctrl_save(gpio)
        try:
            lgpio.gpio_claim_input(h, gpio, lgpio.SET_PULL_UP)
        except lgpio.error:
            print("  " + label + "  belegt (Kernel-Treiber), nicht getestet")
            saved.pop(gpio, None)
            continue
        gpios.append(gpio)
        labels.append(label)

    print("%d Pins mit Pull-Up aktiv. Pin mit GND verbinden -> Meldung." % len(gpios))
    for label in labels:
        print("  " + label)
    print("Pins, die sofort gemeldet werden, lagen schon beim Start auf GND")
    print("(Kurzschluss oder angeschlossene Hardware zieht sie runter).")
    print()

    n = len(gpios)
    reported_low = [False] * n  # last level that was printed
    raw_low = [False] * n       # last level read
    raw_since = [0] * n         # time in ms when raw_low last changed
    start = time.monotonic()

    try:
        while True:
            now = (time.monotonic() - start) * 1000

            for i in range(n):
                low = lgpio.gpio_read(h, gpios[i]) == 0

                if low != raw_low[i]:
                    raw_low[i] = low
                    raw_since[i] = now
                elif low != reported_low[i] and now - raw_since[i] >= DEBOUNCE_MS:
                    reported_low[i] = low
                    print("[%8d ms] %s  -> %s" % (
                        now,
                        labels[i],
                        "mit GND verbunden" if low else "wieder offen",
                    ))

            time.sleep(0.001)
    except KeyboardInterrupt:
        print("stopped")
    finally:
        lgpio.gpiochip_close(h)
        if have_pinctrl:
            pinctrl_restore(saved)
            print("Pin-Modi wiederhergestellt (pinctrl).")
        else:
            print("pinctrl nicht gefunden: Pi neu starten, damit SPI/UART/I2C "
                  "wieder funktionieren.")


if __name__ == "__main__":
    main()

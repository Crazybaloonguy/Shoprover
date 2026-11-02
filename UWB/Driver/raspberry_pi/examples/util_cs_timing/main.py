"""
examples/util_cs_timing/main.py

Checks whether the DW3000 sees CSn go high between back-to-back SPI
transfers on this Pi. Reads DEV_ID six times in a row with shrinking pauses
between the transfers. Every read must return 0xDECA0302; if the chip misses
the CS gap, consecutive reads continue one long transfer instead and return
shifted garbage.

Needs only SPI + power to the DWM3000EVB (no RSTn/IRQ/WAKEUP) and
python3-spidev. From the Driver/ folder:
    python3 raspberry_pi/examples/util_cs_timing/main.py
"""

import os
import platform
import time

import spidev

APP_NAME = "CS TIMING (Raspberry Pi) v0.1"

SPI_BUS = 0
SPI_CS = 0      # CE0 = GPIO8
SPEEDS_HZ = (2_000_000, 16_000_000)
PAUSES_S = (0.02, 0.001, 0.0001, 0)
READS = 6

KNOWN_DEV_IDS = (0xDECA0302, 0xDECA0312)


def main():
    print(APP_NAME)
    print("Kernel:  %s" % platform.release())
    print("spidev:  %s" % getattr(spidev, "__version__", "?"))
    try:
        with open("/proc/device-tree/model") as f:
            print("Board:   %s" % f.read().strip("\x00\n"))
    except OSError:
        pass
    try:
        print("SPI-Geraete: %s" % " ".join(sorted(d for d in os.listdir("/dev") if d.startswith("spidev"))))
    except OSError:
        pass

    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_CS)
    spi.mode = 0
    spi.bits_per_word = 8

    results = {}
    try:
        for hz in SPEEDS_HZ:
            spi.max_speed_hz = hz
            print()
            print("SPI %d kHz:" % (hz // 1000))
            for pause in PAUSES_S:
                ids = []
                for _ in range(READS):
                    rx = spi.xfer2([0, 0, 0, 0, 0])
                    ids.append(int.from_bytes(bytes(rx[1:]), "little"))
                    if pause:
                        time.sleep(pause)
                ok = all(i in KNOWN_DEV_IDS for i in ids)
                results[(hz, pause)] = ok
                print("  Pause %-8s %s  %s" % (
                    "%g ms" % (pause * 1000), " ".join("%08x" % i for i in ids),
                    "OK" if ok else "FEHLER"))
                time.sleep(0.05)   # let the chip settle before the next pause value
    finally:
        spi.close()

    print()
    long_ok = all(results[(hz, PAUSES_S[0])] for hz in SPEEDS_HZ)
    short_ok = all(results[(hz, PAUSES_S[-1])] for hz in SPEEDS_HZ)
    if long_ok and short_ok:
        print("Ergebnis: alle Lesungen OK -- CS-Timing ist NICHT die Ursache.")
    elif long_ok:
        print("Ergebnis: OK mit langer Pause, FEHLER bei kurzer/keiner Pause -- der Chip")
        print("bemerkt das CS-Hochgehen zwischen schnellen Transfers nicht.")
    else:
        print("Ergebnis: schon mit 20 ms Pause FEHLER -- Grundproblem der SPI-Verbindung.")
    print("Bitte die komplette Ausgabe schicken.")


if __name__ == "__main__":
    main()

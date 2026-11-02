"""
examples/util_cs_timing/main.py

Checks whether the DW3000 sees CSn go high between back-to-back SPI
transfers on this Pi. Reads DEV_ID six times in a row with shrinking pauses
between the transfers. Every read must return 0xDECA0302; if the chip misses
the CS gap, consecutive reads continue one long transfer instead and return
shifted garbage.

The same series runs twice:
  A) through python-spidev's xfer2(), as the driver does;
  B) through the raw spidev ioctl (SPI_IOC_MESSAGE), bypassing python-spidev,
     with cs_change = 0 set explicitly ("release CS after the transfer").
A fails but B works -> python-spidev keeps CS asserted; the driver can use
the raw ioctl instead. Both fail -> the kernel / SPI driver does not release
CS between messages.

Needs only SPI + power to the DWM3000EVB (no RSTn/IRQ/WAKEUP) and
python3-spidev. From the Driver/ folder:
    python3 raspberry_pi/examples/util_cs_timing/main.py
"""

import ctypes
import fcntl
import os
import platform
import struct
import time

import spidev

APP_NAME = "CS TIMING (Raspberry Pi) v0.2"

SPI_BUS = 0
SPI_CS = 0      # CE0 = GPIO8
SPEEDS_HZ = (2_000_000, 16_000_000)
PAUSES_S = (0.02, 0.001, 0.0001, 0)
READS = 6

KNOWN_DEV_IDS = (0xDECA0302, 0xDECA0312)

# linux/spi/spidev.h
SPI_IOC_WR_MODE = 0x40016B01            # _IOW('k', 1, __u8)
SPI_IOC_MESSAGE_1 = 0x40206B00          # _IOW('k', 0, struct spi_ioc_transfer[1])
# struct spi_ioc_transfer: tx_buf, rx_buf (u64), len, speed_hz (u32),
# delay_usecs (u16), bits_per_word, cs_change, tx_nbits, rx_nbits,
# word_delay_usecs, pad (u8) -- 32 bytes.
_SPI_IOC_TRANSFER = struct.Struct("=QQIIHBBBBBB")


class RawSpi:
    """Minimal spidev access through the ioctl, without python-spidev."""

    def __init__(self, bus, cs):
        self.fd = os.open("/dev/spidev%d.%d" % (bus, cs), os.O_RDWR)
        fcntl.ioctl(self.fd, SPI_IOC_WR_MODE, struct.pack("B", 0))
        self.speed_hz = 2_000_000

    def xfer(self, data):
        n = len(data)
        tx = ctypes.create_string_buffer(bytes(data), n)
        rx = ctypes.create_string_buffer(n)
        tr = _SPI_IOC_TRANSFER.pack(ctypes.addressof(tx), ctypes.addressof(rx), n,
                                    self.speed_hz, 0, 8, 0, 0, 0, 0, 0)
        fcntl.ioctl(self.fd, SPI_IOC_MESSAGE_1, tr)
        return list(rx.raw)

    def close(self):
        os.close(self.fd)


def run_series(title, set_speed, xfer):
    """Returns {(hz, pause): ok}."""
    print()
    print(title)
    results = {}
    for hz in SPEEDS_HZ:
        set_speed(hz)
        print("  SPI %d kHz:" % (hz // 1000))
        for pause in PAUSES_S:
            ids = []
            for _ in range(READS):
                rx = xfer([0, 0, 0, 0, 0])
                ids.append(int.from_bytes(bytes(rx[1:]), "little"))
                if pause:
                    time.sleep(pause)
            ok = all(i in KNOWN_DEV_IDS for i in ids)
            results[(hz, pause)] = ok
            print("    Pause %-8s %s  %s" % (
                "%g ms" % (pause * 1000), " ".join("%08x" % i for i in ids),
                "OK" if ok else "FEHLER"))
            time.sleep(0.05)   # let the chip settle before the next pause value
    return results


def short_ok(results):
    return all(results[(hz, PAUSES_S[-1])] for hz in SPEEDS_HZ)


def print_cs_owner():
    """Show who drives CE0 (kernel GPIO CS or native SPI CS); needs root."""
    try:
        with open("/sys/kernel/debug/gpio") as f:
            lines = [l.strip() for l in f if "spi" in l.lower() or "gpio-8 " in l]
        print("CS-Leitungen (debugfs): %s" % ("; ".join(lines) if lines else "keine GPIO-CS gefunden"))
    except OSError:
        print("CS-Leitungen (debugfs): nicht lesbar (mit sudo starten fuer diese Info)")


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
    print_cs_owner()

    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_CS)
    spi.mode = 0
    spi.bits_per_word = 8
    try:
        res_a = run_series("A) python-spidev xfer2():",
                           lambda hz: setattr(spi, "max_speed_hz", hz), spi.xfer2)
    finally:
        spi.close()

    raw = RawSpi(SPI_BUS, SPI_CS)
    try:
        res_b = run_series("B) direkter ioctl, cs_change = 0:",
                           lambda hz: setattr(raw, "speed_hz", hz), raw.xfer)
    finally:
        raw.close()

    print()
    if short_ok(res_a):
        print("Ergebnis: A ohne Pause OK -- CS-Timing ist NICHT die Ursache.")
    elif short_ok(res_b):
        print("Ergebnis: A FEHLER, B OK -- python-spidev laesst CS aktiv. Loesung: der")
        print("Treiber benutzt den direkten ioctl (wie Teil B).")
    elif all(res_b[(hz, PAUSES_S[0])] for hz in SPEEDS_HZ):
        print("Ergebnis: A und B ohne Pause FEHLER -- Kernel/SPI-Treiber gibt CS zwischen")
        print("schnellen Transfers nicht frei. Loesung: CS von Hand steuern (wie Pico).")
    else:
        print("Ergebnis: auch B mit 20 ms Pause FEHLER -- Teil B selbst pruefen.")
    print("Bitte die komplette Ausgabe schicken.")


if __name__ == "__main__":
    main()

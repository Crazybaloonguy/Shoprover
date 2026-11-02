"""
examples/util_init_check/main.py

Step-by-step replay of the start-up every ranging example does
(spi_set_rate_high, reset_dwic, dwt_checkidlerc, dwt_initialise), printing
what the DW3000 returns at each step. For finding out why an example stops
with "INIT FAILED" although util_read_dev_id_spi_only reads a valid DEV_ID.

Run from the Driver/ folder:
    python3 raspberry_pi/examples/util_init_check/main.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(_HERE, "..", ".."), os.path.join(_HERE, "..", "..", "..")]

import utime as time

from dw_platform import port as port_module
from dw_platform.port import port
from decadriver import deca_device as dwt
from decadriver import deca_regs as R

APP_NAME = "INIT CHECK (Raspberry Pi) v0.1"

GOOD_IDS = (R.DWT_C0_DEV_ID, R.DWT_C0_PDOA_DEV_ID)


def devid_line(label):
    ids = [dwt.dwt_readdevid() for _ in range(5)]
    ok = all(i in GOOD_IDS for i in ids)
    print("  %-36s %s  %s" % (label, " ".join("%08x" % i for i in ids),
                              "OK" if ok else "FEHLER"))
    return ok


def levels_line(label):
    irq = port.irq.value() if port.irq is not None else "-"
    rst = port.rst.value()
    print("  %-36s RSTn=%s  IRQ=%s%s" % (
        label, rst, irq, "" if rst else "   <- RSTn low: chip is held in reset!"))


def status_line(label):
    status = dwt.dwt_read32bitreg(R.SYS_STATUS_ID)
    print("  %-36s SYS_STATUS 0x%08x  (RCINIT=%d)" % (
        label, status, 1 if status & R.SYS_STATUS_RCINIT_BIT_MASK else 0))


def idle_wait():
    """dwt_checkidlerc() loop with a time limit; returns ms waited or None."""
    t0 = time.ticks_ms()
    while not dwt.dwt_checkidlerc():
        if time.ticks_diff(time.ticks_ms(), t0) > 500:
            return None
    return time.ticks_diff(time.ticks_ms(), t0)


def run_startup(label, set_rate):
    print()
    print(label)
    set_rate()
    print("  SPI-Takt eingestellt:               %d Hz" % port.spi.max_speed_hz)
    levels_line("Leitungen vor reset_dwic():")
    port.reset_dwic()
    time.sleep_ms(2)
    levels_line("Leitungen nach reset_dwic():")
    status_line("nach reset_dwic():")
    waited = idle_wait()
    print("  dwt_checkidlerc():                  %s" % (
        "IDLE_RC nach %d ms" % waited if waited is not None else "NIE erreicht (500 ms)"))
    devid_line("DEV_ID (5x):")
    ret = dwt.dwt_initialise(R.DWT_DW_INIT)
    print("  dwt_initialise():                   %s" % (
        "OK" if ret == R.DWT_SUCCESS else "FEHLER (= INIT FAILED)"))
    return ret == R.DWT_SUCCESS


def main():
    print(APP_NAME)
    print()
    print("Dateien auf diesem Pi:")
    print("  %s" % os.path.abspath(port_module.__file__))
    print("  SPI_SLOW_HZ = %d, SPI_FAST_HZ = %d" % (port_module.SPI_SLOW_HZ, port_module.SPI_FAST_HZ))
    print("  CSn %s, RSTn GPIO%s, IRQ GPIO%s" % (
        "GPIO%d (von Hand)" % port.pins["cs"] if port.pins.get("cs") is not None else "CE0 (Kernel)",
        port.pins["rst"], port.pins["irq"]))

    slow_ok = run_startup("1) Start mit langsamem SPI (wie ex_00a):", port.spi_set_rate_low)
    fast_ok = run_startup("2) Start mit schnellem SPI (wie ex_05b):", port.spi_set_rate_high)

    print()
    print("Takt-Test (ohne Reset, DEV_ID 5x je Takt):")
    for hz in (500_000, 1_000_000, 2_000_000, 4_000_000, 8_000_000, 16_000_000):
        port.spi.max_speed_hz = hz
        devid_line("%5.1f MHz:" % (hz / 1e6))
    port.spi_set_rate_low()

    print()
    if slow_ok and fast_ok:
        print("Ergebnis: Initialisierung klappt in beiden Faellen.")
        print("Laeuft ex_05b trotzdem nicht, dessen Ausgabe schicken.")
    elif slow_ok:
        print("Ergebnis: nur mit langsamem SPI OK -> SPI_FAST_HZ in dw_platform/port.py")
        print("auf den hoechsten Takt setzen, der oben im Takt-Test OK war.")
    else:
        print("Ergebnis: Initialisierung schlaegt auch langsam fehl -> Ausgabe schicken.")


if __name__ == "__main__":
    main()

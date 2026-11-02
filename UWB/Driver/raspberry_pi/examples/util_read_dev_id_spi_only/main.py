"""
examples/util_read_dev_id_spi_only/main.py

Read the DW3000 DEV_ID from a DWM3000EVB wired to a Raspberry Pi 4 with only
SPI + power -- no RSTn, IRQ or WAKEUP. A wiring check before running the
driver.

Self-contained (does not import decadriver/dw_platform, needs only
python3-spidev): python3 examples/util_read_dev_id_spi_only/main.py
Stop with Ctrl-C.

Wiring (same as dw_platform/port.py):

    DWM3000EVB          Raspberry Pi 4
    SPI CLK  (D13)  ->  GPIO11 (pin 23)
    SPI MISO (D12)  ->  GPIO9  (pin 21)
    SPI MOSI (D11)  ->  GPIO10 (pin 19)
    SPI CSn  (D10)  ->  GPIO8  (pin 24, CE0)
    3V3             ->  3V3    (pin 17)   EVB jumper J1 "up" (3V3 from header)
    GND             ->  GND    (pin 20)

Leaving RSTn open is fine: the DWM3000 data sheet lists RSTn as an
active-low *output* of the chip, which resets itself on power-up (POR,
< 1 ms) and only needs RSTn for an external hard reset. Without it, the only
way to reset the chip is to cut its power.

DEV_ID is register file 0, offset 0, so the read is a one-byte "fast access"
header 0x00 followed by 4 data bytes, little-endian -- the same transaction
decadriver's dwt_readdevid() produces (dwt_xfer3000, FARW mode).

Unlike the Pico version there is no per-wire line check with the GPIO pulls:
while SPI is enabled the kernel owns the SPI pins (CE0 is even claimed as a
GPIO), so they can't be switched to inputs from here. Use util_pin_test for
continuity checks.
"""

import time

import spidev

APP_NAME = "READ DEV ID, SPI only (Raspberry Pi) v0.1"

SPI_BUS = 0
SPI_CS = 0      # CE0 = GPIO8

# 2 MHz is the driver's pre-init rate (port.py SPI_SLOW_HZ); 500 kHz is a
# fallback for long or loose jumper wires.
SPEEDS_HZ = (2_000_000, 500_000)
READS_PER_SPEED = 5

DEV_ID_HEADER = [0x00]
KNOWN_DEV_IDS = {
    0xDECA0302: "DW3000 C0 (DW3110, as on the DWM3000)",
    0xDECA0312: "DW3000 C0 with PDOA (DW3120)",
}


def read_dev_id(spi):
    rx = spi.xfer2(DEV_ID_HEADER + [0] * 4)
    raw = bytes(rx[1:])
    return raw, int.from_bytes(raw, "little")


def explain(raw, dev_id):
    if dev_id in KNOWN_DEV_IDS:
        return "OK: " + KNOWN_DEV_IDS[dev_id]
    if raw == b"\xff\xff\xff\xff":
        return ("FEHLER: nur 0xFF -- MISO (GPIO9) nicht verbunden, CSn (GPIO8) "
                "nicht verbunden, oder Modul ohne Strom (3V3/GND, Jumper J1)")
    if raw == b"\x00\x00\x00\x00":
        return ("FEHLER: nur 0x00 -- MISO haengt auf GND, MISO nicht verbunden, "
                "oder Modul ohne Strom (3V3/GND, Jumper J1)")
    if dev_id >> 16 == 0xDECA:
        return "WARNUNG: DECAWAVE-Chip, aber unbekannte Variante"
    return ("FEHLER: unplausibler Wert -- SCK (GPIO11) / MOSI (GPIO10) pruefen, "
            "evtl. vertauscht, oder Kabel zu lang/wackelig")


def main():
    print(APP_NAME)

    spi = spidev.SpiDev()
    try:
        spi.open(SPI_BUS, SPI_CS)
    except FileNotFoundError:
        print("FEHLER: /dev/spidev%d.%d fehlt -- SPI mit sudo raspi-config "
              "(Interface Options -> SPI) aktivieren und neu starten." % (SPI_BUS, SPI_CS))
        return
    spi.mode = 0
    spi.bits_per_word = 8

    ok_speed = None
    for hz in SPEEDS_HZ:
        spi.max_speed_hz = hz
        print()
        print("SPI %d kHz:" % (hz // 1000))
        values = set()
        for i in range(READS_PER_SPEED):
            raw, dev_id = read_dev_id(spi)
            values.add(dev_id)
            print("  #%d  raw %s  DEV_ID 0x%08x" % (
                i + 1, " ".join("%02x" % b for b in raw), dev_id))
            time.sleep(0.02)

        if len(values) > 1:
            print("  WARNUNG: Werte schwanken -- Wackelkontakt auf einer SPI-Leitung?")
        print("  " + explain(raw, dev_id))

        if len(values) == 1 and dev_id in KNOWN_DEV_IDS:
            ok_speed = hz
            break

    print()
    if ok_speed is None:
        print("Ergebnis: DEV_ID NICHT gelesen. Verkabelung pruefen (siehe oben).")
    else:
        print("Ergebnis: DEV_ID 0x%08x bei %d kHz gelesen -- SPI funktioniert."
              % (dev_id, ok_speed // 1000))
        if ok_speed != SPEEDS_HZ[0]:
            print("Hinweis: nur bei niedrigem Takt stabil -- Kabel kuerzen.")
        spi.max_speed_hz = ok_speed

    # Keep reading so wires can be wiggled; only changes are printed.
    print()
    print("Dauertest: liest alle 200 ms, meldet nur Aenderungen (Ctrl-C = Ende).")
    last = None
    count = 0
    try:
        while True:
            raw, dev_id = read_dev_id(spi)
            count += 1
            if dev_id != last:
                print("  [Lesung %d] DEV_ID 0x%08x  %s" % (count, dev_id, explain(raw, dev_id)))
                last = dev_id
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("stopped after %d reads" % count)
    finally:
        spi.close()


if __name__ == "__main__":
    main()

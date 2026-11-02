"""
examples/util_read_dev_id_spi_only/main.py

Read the DW3000 DEV_ID from a DWM3000EVB wired to a Raspberry Pi Pico 2 W
with only SPI + power -- no RSTn, IRQ or WAKEUP. A wiring check before
running the driver.

Self-contained (does not import decadriver/dw_platform), so in Thonny just open
it and press Run. Stop with Ctrl-C (or Thonny's Stop button).

Wiring (same GPIOs as dw_platform/port.py):

    DWM3000EVB          Pico 2 W
    SPI CLK  (D13)  ->  GP18  (pin 24)
    SPI MISO (D12)  ->  GP16  (pin 21)
    SPI MOSI (D11)  ->  GP19  (pin 25)
    SPI CSn  (D10)  ->  GP17  (pin 22)
    3V3             ->  3V3   (pin 36)   EVB jumper J1 "up" (3V3 from header)
    GND             ->  GND   (e.g. pin 23)

Leaving RSTn open is fine: the DWM3000 data sheet lists RSTn as an
active-low *output* of the chip, which resets itself on power-up (POR,
< 1 ms) and only needs RSTn for an external hard reset. Without it, the only
way to reset the chip is to cut its power.

DEV_ID is register file 0, offset 0, so the read is a one-byte "fast access"
header 0x00 followed by 4 data bytes, little-endian -- the same transaction
decadriver's dwt_readdevid() produces (dwt_xfer3000, FARW mode).

Before the SPI read, a line check tests each wire on its own, using the
DW3000's internal pulls (DWM3000 data sheet 6.3: pull-down on SPICLK/SPIMOSI,
pull-up on SPICSn, 10-30 kOhm -- stronger than the RP2350's ~50 kOhm pulls,
so they win against the opposite Pico pull):
  - CSn reads high against a Pico pull-down -> wire connected AND module
    powered (the pull-up goes to the DW3000's own supply).
  - SCK / MOSI read low against a Pico pull-up -> wire connected.
  - MISO, with CSn low, keeps its level whichever Pico pull is enabled ->
    the chip is driving it. If it just follows the Pico pull, nothing drives
    it.
"""

import utime as time
from machine import Pin, SPI

APP_NAME = "READ DEV ID, SPI only v0.1"

SPI_ID = 0
SCK = 18
MOSI = 19
MISO = 16
CS = 17

# 2 MHz is the driver's pre-init rate (port.py SPI_SLOW_HZ); 500 kHz is a
# fallback for long or loose jumper wires.
SPEEDS_HZ = (2_000_000, 500_000)
READS_PER_SPEED = 5

DEV_ID_HEADER = b"\x00"
KNOWN_DEV_IDS = {
    0xDECA0302: "DW3000 C0 (DW3110, as on the DWM3000)",
    0xDECA0312: "DW3000 C0 with PDOA (DW3120)",
}


def read_with_pull(gpio, pull, predrive=True):
    # Drive the pad to the pull's own level first, so the reading starts from
    # a known state (RP2350 erratum E9: a pad left high with only the
    # pull-down enabled can stay stuck near 2 V and read as 1).
    if predrive:
        Pin(gpio, Pin.OUT, value=1 if pull == Pin.PULL_UP else 0)
    p = Pin(gpio, Pin.IN, pull)
    time.sleep_ms(2)
    return p.value()


def line_check():
    """Check each SPI wire via the DW3000's internal pulls. Returns True if
    nothing looked wrong."""
    print()
    print("Leitungscheck (vor SPI):")
    ok = True

    cs_high = read_with_pull(CS, Pin.PULL_DOWN)
    if cs_high:
        print("  CSn  (GP17): Pull-Up vom DW3000 erkannt -> verbunden, Modul hat Strom")
    else:
        print("  CSn  (GP17): KEIN Pull-Up -> CSn-Kabel offen/falscher Pin, "
              "ODER Modul ohne Strom (3V3/GND, Jumper J1)")
        ok = False

    for name, gpio in (("SCK ", SCK), ("MOSI", MOSI)):
        if read_with_pull(gpio, Pin.PULL_UP) == 0:
            print("  %s (GP%d): Pull-Down vom DW3000 erkannt -> verbunden" % (name, gpio))
        else:
            print("  %s (GP%d): KEIN Pull-Down -> Kabel offen oder falscher Pin" % (name, gpio))
            ok = False

    # MISO: select the chip, then see whether the level depends on the Pico's
    # pull. Park the pad low first while the chip is deselected (MISO
    # tristated), and read with the pull-down first, so E9 can't fake a 1.
    # The selected readings are not pre-driven -- the chip may be driving.
    read_with_pull(MISO, Pin.PULL_DOWN)
    cs = Pin(CS, Pin.OUT, value=0)
    time.sleep_ms(1)
    miso_pd = read_with_pull(MISO, Pin.PULL_DOWN, predrive=False)
    miso_pu = read_with_pull(MISO, Pin.PULL_UP, predrive=False)
    cs.value(1)
    if miso_pd == miso_pu:
        print("  MISO (GP16): bei CSn=low vom Chip getrieben (Pegel %d) -> verbunden" % miso_pu)
    else:
        print("  MISO (GP16): folgt nur dem Pico-Pull -> Kabel offen/falscher Pin, "
              "oder Chip antwortet nicht (CSn/Strom)")
        ok = False

    return ok


def read_dev_id(spi, cs):
    cs.value(0)
    try:
        spi.write(DEV_ID_HEADER)
        raw = spi.read(4)
    finally:
        cs.value(1)
    return raw, int.from_bytes(raw, "little")


def explain(raw, dev_id):
    if dev_id in KNOWN_DEV_IDS:
        return "OK: " + KNOWN_DEV_IDS[dev_id]
    if raw == b"\xff\xff\xff\xff":
        return ("FEHLER: nur 0xFF -- MISO (GP16) nicht verbunden, CSn (GP17) "
                "nicht verbunden, oder Modul ohne Strom (3V3/GND, Jumper J1)")
    if raw == b"\x00\x00\x00\x00":
        return ("FEHLER: nur 0x00 -- MISO haengt auf GND oder Modul ohne "
                "Strom (3V3/GND, Jumper J1)")
    if dev_id >> 16 == 0xDECA:
        return "WARNUNG: DECAWAVE-Chip, aber unbekannte Variante"
    return ("FEHLER: unplausibler Wert -- SCK (GP18) / MOSI (GP19) pruefen, "
            "evtl. vertauscht, oder Kabel zu lang/wackelig")


def main():
    print(APP_NAME)

    time.sleep_ms(10)  # in case the EVB was powered together with the Pico
    line_check()

    cs = Pin(CS, Pin.OUT, value=1)
    # Pull-up on MISO so an unconnected or unselected MISO (the DW3000 tristates
    # it while CSn is high) reads a clean 0xFF instead of random noise.
    Pin(MISO, Pin.IN, Pin.PULL_UP)
    spi = SPI(SPI_ID, baudrate=SPEEDS_HZ[0], polarity=0, phase=0, bits=8,
              firstbit=SPI.MSB, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))

    ok_speed = None
    for hz in SPEEDS_HZ:
        spi.init(baudrate=hz)
        print()
        print("SPI %d kHz:" % (hz // 1000))
        values = set()
        for i in range(READS_PER_SPEED):
            raw, dev_id = read_dev_id(spi, cs)
            values.add(dev_id)
            print("  #%d  raw %s  DEV_ID 0x%08x" % (
                i + 1, " ".join("%02x" % b for b in raw), dev_id))
            time.sleep_ms(20)

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
        spi.init(baudrate=ok_speed)

    # Keep reading so wires can be wiggled; only changes are printed.
    print()
    print("Dauertest: liest alle 200 ms, meldet nur Aenderungen (Ctrl-C = Ende).")
    last = None
    count = 0
    try:
        while True:
            raw, dev_id = read_dev_id(spi, cs)
            count += 1
            if dev_id != last:
                print("  [Lesung %d] DEV_ID 0x%08x  %s" % (count, dev_id, explain(raw, dev_id)))
                last = dev_id
            time.sleep_ms(200)
    except KeyboardInterrupt:
        print("stopped after %d reads" % count)


if __name__ == "__main__":
    main()

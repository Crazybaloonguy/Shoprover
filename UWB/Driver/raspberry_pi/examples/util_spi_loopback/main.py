"""
examples/util_spi_loopback/main.py

SPI loopback test for the Raspberry Pi 4: checks that the Pi actually drives
MOSI, without the DWM3000 in the way.

Setup: UNPLUG the DWM3000EVB, then connect a single jumper wire from
    pin 19 (GPIO10, MOSI)  to  pin 21 (GPIO9, MISO).
Every byte the Pi sends on MOSI then comes straight back on MISO.

Self-contained (needs only python3-spidev). From the Driver/ folder:
    python3 raspberry_pi/examples/util_spi_loopback/main.py
"""

import spidev

APP_NAME = "SPI LOOPBACK (Raspberry Pi) v0.1"

SPI_BUS = 0
SPI_CS = 0      # CE0 = GPIO8 (not needed for the loopback, but opened anyway)

SPEEDS_HZ = (500_000, 2_000_000, 16_000_000)

# 0x41 0x10 is the SYS_STATUS read header from the INIT FAILED case; the rest
# toggles every bit both ways.
PATTERNS = (
    [0x41, 0x10, 0xA5, 0x5A],
    [0x00, 0xFF, 0x00, 0xFF],
    [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80],
)


def hexs(data):
    return " ".join("%02x" % b for b in data)


def explain(results):
    """results: list of (sent, received) that did not match."""
    received = [b for _, rx in results for b in rx]
    if all(b == 0x00 for b in received):
        return ("nur 0x00 -- MOSI (Pin 19) sendet nichts oder die Bruecke fehlt. "
                "Pin-Modus von GPIO10 pruefen (nach util_pin_test: sudo reboot).")
    if all(b == 0xFF for b in received):
        return ("nur 0xFF -- MISO (Pin 21) liest nur High: Bruecke fehlt oder "
                "steckt auf dem falschen Pin.")
    return ("Daten verfaelscht -- Wackelkontakt, falscher Pin oder Kabel zu lang "
            "(nur bei hohem Takt? -> Kabel kuerzen).")


def main():
    print(APP_NAME)
    print("Aufbau: EVB abgesteckt, Kabel von Pin 19 (MOSI) nach Pin 21 (MISO).")

    spi = spidev.SpiDev()
    try:
        spi.open(SPI_BUS, SPI_CS)
    except FileNotFoundError:
        print("FEHLER: /dev/spidev%d.%d fehlt -- SPI aktivieren: dtparam=spi=on in "
              "/boot/firmware/config.txt eintragen und neu starten." % (SPI_BUS, SPI_CS))
        return
    except PermissionError:
        print("FEHLER: kein Zugriff auf /dev/spidev%d.%d -- mit sudo starten oder "
              "Zugriffsrechte einrichten (README, Installation Schritt 3)." % (SPI_BUS, SPI_CS))
        return
    spi.mode = 0
    spi.bits_per_word = 8

    all_ok = True
    try:
        for hz in SPEEDS_HZ:
            spi.max_speed_hz = hz
            print()
            print("SPI %d kHz:" % (hz // 1000))
            failed = []
            for pattern in PATTERNS:
                rx = spi.xfer2(list(pattern))
                ok = rx == pattern
                print("  gesendet %-24s empfangen %-24s %s" % (
                    hexs(pattern), hexs(rx), "OK" if ok else "FEHLER"))
                if not ok:
                    failed.append((pattern, rx))
            if failed:
                all_ok = False
                print("  -> " + explain(failed))
    finally:
        spi.close()

    print()
    if all_ok:
        print("Ergebnis: Loopback OK -- der Pi sendet auf MOSI (Pin 19) korrekt.")
        print("Liest der DWM3000 trotzdem 0x00deca03 statt DEV_ID: Fehler liegt zwischen")
        print("Pin 19 und dem Chip (Kabel tauschen, Kontakt D11 am EVB pruefen).")
    else:
        print("Ergebnis: Loopback FEHLER -- siehe Hinweise oben.")


if __name__ == "__main__":
    main()

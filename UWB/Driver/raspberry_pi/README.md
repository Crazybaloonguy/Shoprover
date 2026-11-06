DWM3000 Python Treiber (Raspberry Pi 4)
---

Python-Treiber und Beispielprogramme für den Qorvo DW3000 (UWB) auf einem
**Raspberry Pi 4** mit **Ubuntu 24.04** und einem **DWM3000EVB**.

Der Treiber ist derselbe wie auf dem Pico (`pico_pi/`), nur die Hardware-Schicht
`dw_platform/` ist für Linux geschrieben (SPI über `spidev`, GPIO über `lgpio`).
Dieser Ordner ist eigenständig: Auf dem Pi wird nur `raspberry_pi/` gebraucht.

| Ordner / Datei | Inhalt |
|---|---|
| `decadriver/` | DW3000-Treiber (wie auf dem Pico) |
| `shared_data/`, `config_options.py` | Hilfsfunktionen und TX-Einstellungen (wie auf dem Pico) |
| `dw_platform/` | Pi-spezifisch: Pins, SPI, Reset, IRQ |
| `utime.py` | Ersatz für das MicroPython-Modul `utime` |
| `run.py` | Startet ein Beispiel |
| `examples/` | Beispielprogramme |

---
## Installation

1. Pakete installieren

   ```bash
   sudo apt install python3-spidev python3-lgpio
   ```

2. SPI ohne Kernel-Chip-Select aktivieren

   Der Treiber steuert CSn selbst über GPIO8. Damit der Kernel den Pin nicht belegt,
   in `/boot/firmware/config.txt` die Zeile `dtparam=spi=on` auskommentieren und am Ende ergänzen:

   ```
   dtoverlay=spi0-0cs
   ```

   Danach neu starten und prüfen:

   ```bash
   ls /dev/spidev0.0              # muss vorhanden sein
   gpioinfo | grep '"GPIO8"'      # muss "unused" zeigen
   ```

   Note: Fehlt `/dev/spidev0.0`, `dtparam=spi=on` wieder einkommentieren und `dtoverlay=spi0-0cs` darunter stehen lassen.

3. DWM3000EVB mit dem Pi verkabeln

   | DWM3000EVB | Raspberry Pi 4 |
   |---|---|
   | SPI CLK | GPIO11 (Pin 23) |
   | SPI MISO | GPIO9 (Pin 21) |
   | SPI MOSI | GPIO10 (Pin 19) |
   | SPI CSn | GPIO8 (Pin 24) |
   | 3V3 | 3V3 (Pin 1) |
   | GND | GND (z. B. Pin 6) |
   | RSTn | GPIO25 (Pin 22) |
   | IRQ, optional | GPIO24 (Pin 18) |
   | WAKEUP, optional | GPIO23 (Pin 16) |

   **Jumper J1 auf dem EVB auf „Up“** stellen, damit das Modul die 3,3 V vom Pi bekommt.

   Note: GPIO-Nummer und Pin-Nummer nicht verwechseln: GPIO25 ist Pin 22, Pin 25 ist GND.

   Andere Verkabelung: `PINS` in `dw_platform/port.py` anpassen.

4. Ordner `raspberry_pi/` auf den Pi kopieren (z. B. per `git clone` oder `scp`).

# Beispiele

Starten mit `run.py`, stoppen mit `Strg+C`:

```bash
python3 run.py                          # listet alle Beispiele
python3 run.py ex_00a_reading_dev_id
```

Note: Bei `Permission denied` auf `/dev/spidev0.0` oder `/dev/gpiochip0` mit `sudo` starten.

Die Beispiele sind dieselben wie auf dem Pico und passen zueinander, d. h. ein Beispiel
auf dem Pi kann mit seinem Gegenstück auf dem Pico arbeiten.

1. Verbindung testen

   ```
   python3 run.py ex_00a_reading_dev_id      DEV_ID lesen
   python3 run.py util_read_chip_id          Part ID / Lot ID lesen
   ```

   Erwartete Ausgabe: DEV_ID `0xdeca0302`

2. Senden und Empfangen

   ```
   Gerät 1:  ex_02a_simple_rx
   Gerät 2:  ex_01a_simple_tx
   ```

3. Entfernungsmessung

   Den Responder immer zuerst starten.

   ```
   Gerät 1:  ex_06b_ss_twr_responder
   Gerät 2:  ex_06a_ss_twr_initiator
   ```

   oder (Double-Sided)

   ```
   Gerät 1:  ex_05b_ds_twr_responder
   Gerät 2:  ex_05a_ds_twr_initiator
   ```

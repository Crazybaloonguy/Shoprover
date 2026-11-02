DWM3000 Python Treiber (Raspberry Pi 4)
---

Python-Treiber und Beispielprogramme für den Qorvo DW3000 (UWB) auf einem
**Raspberry Pi 4** mit einem **DWM3000EVB**.

Der Treiber selbst (`decadriver/`, `shared_data/`, `config_options.py`) und die Beispiele liegen gemeinsam für
Pico und Pi in [`Driver/`](..). Dieser Ordner enthält nur die Pi-spezifischen Teile:

| | Pico (MicroPython), [`../pico_pi`](../pico_pi) | Raspberry Pi 4 (CPython), dieser Ordner |
|---|---|---|
| Hardware-Schicht | `dw_platform/` | `dw_platform/` |
| SPI | `machine.SPI`, CS per GPIO | `spidev` (`/dev/spidev0.0`), CS = Hardware-CE0 |
| GPIO / IRQ | `machine.Pin`, Soft-IRQ | `lgpio`, Callback-Thread + Lock |
| Zeit | `utime` (eingebaut) | [`utime.py`](utime.py) (Nachbau mit `time`) |
| Beispiele starten | Thonny | [`run.py`](run.py) |

Weitere Infos zum DW3000 / DWM3000:

dwm3000-micropython (Original): https://github.com/foldedtoad/dwm3000-micropython

Qorvo DWM3000: https://www.qorvo.com/products/p/DWM3000

---
## Installation

1. SPI aktivieren und Pakete installieren (Raspberry Pi OS Bookworm, einmalig)

   ```
   sudo raspi-config        # Interface Options -> SPI -> Enable, danach neu starten
   sudo apt install python3-spidev python3-lgpio
   ```

   Danach muss `/dev/spidev0.0` existieren (`ls /dev/spidev*`).

2. DWM3000EVB mit dem Pi verkabeln

   | DWM3000EVB | Raspberry Pi 4 |
   |---|---|
   | SPI CLK | GPIO11 (Pin 23) |
   | SPI MISO | GPIO9 (Pin 21) |
   | SPI MOSI | GPIO10 (Pin 19) |
   | SPI CSn | GPIO8 / CE0 (Pin 24) |
   | 3V3 | 3V3 (Pin 17) |
   | GND | GND (z. B. Pin 20) |
   | RSTn, optional | GPIO25 (Pin 22) |
   | IRQ, optional | GPIO24 (Pin 18) |
   | WAKEUP, optional | GPIO23 (Pin 16) |

   **Jumper J1 auf dem EVB auf „Up“** stellen, damit das Modul die 3,3 V vom Pi bekommt.

   Andere Pins: `PINS` in [`dw_platform/port.py`](dw_platform/port.py) anpassen.

3. Den ganzen Ordner `Driver/` auf den Pi kopieren (z. B. `git clone` oder `scp -r`), nicht nur `raspberry_pi/`.

# Beispiele

Die gemeinsamen Beispiele (`Driver/examples/`) über `run.py` starten, das die Importpfade setzt.
Name oder Pfad des Beispiels angeben, stoppen mit `Strg+C`:

```
cd Driver
python3 raspberry_pi/run.py ex_00a_reading_dev_id
python3 raspberry_pi/run.py                          # listet alle Beispiele
```

Die zwei Verkabelungstests sind Pi-spezifisch und eigenständig, sie werden direkt gestartet:

```
python3 raspberry_pi/examples/util_pin_test/main.py
python3 raspberry_pi/examples/util_read_dev_id_spi_only/main.py
```

Ist der Benutzer nicht in der Gruppe `spi`/`gpio` (Standardbenutzer ist es), mit `sudo` starten.

1. Verbindung testen

   ```
   raspberry_pi/examples/util_pin_test/main.py               Pins und Kabel prüfen (EVB abstecken)
   raspberry_pi/examples/util_read_dev_id_spi_only/main.py   SPI prüfen, nur SPI-Leitungen nötig
   raspberry_pi/run.py ex_00a_reading_dev_id                 DEV_ID über den Treiber lesen
   ```

   Erwartete Ausgabe: DEV_ID `0xdeca0302`

2. Senden und Empfangen

   ```
   Board 1:  raspberry_pi/run.py ex_02a_simple_rx
   Board 2:  raspberry_pi/run.py ex_01a_simple_tx
   ```

3. Entfernungsmessung

   Den Responder immer zuerst starten.

   ```
   Board 1:  raspberry_pi/run.py ex_06b_ss_twr_responder
   Board 2:  raspberry_pi/run.py ex_06a_ss_twr_initiator
   ```

   oder (Double-Sided)

   ```
   Board 1:  raspberry_pi/run.py ex_05b_ds_twr_responder
   Board 2:  raspberry_pi/run.py ex_05a_ds_twr_initiator
   ```

   Note: Die Boards ein paar Minuten warmlaufen lassen, danach wird die Messung deutlich genauer.

Note: Pi und Pico können gemischt werden, z. B. Responder auf dem Pico, Initiator auf dem Pi.
Beide benutzen dieselben Beispiele und damit dieselbe Funk-Konfiguration.

Note: Linux ist kein Echtzeitsystem. Die Antwortzeiten in den Beispielen sind (wie beim Pico)
großzügig gewählt, einzelne verpasste Antworten durch Scheduler-Verzögerungen sind trotzdem möglich.

---

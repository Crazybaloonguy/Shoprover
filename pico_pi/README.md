DWM3000 MicroPython Treiber (Pico 2 W)
---

MicroPython-Treiber und Beispielprogramme für den Qorvo DW3000 (UWB) auf einem
**Raspberry Pi Pico 2 W** mit einem **DWM3000EVB**

Weitere Infos zum DW3000 / DWM3000:

dwm3000-micropython (Original): https://github.com/foldedtoad/dwm3000-micropython

Qorvo DWM3000: https://www.qorvo.com/products/p/DWM3000

Thonny: https://thonny.org

Datenblätter und User Manual: [docs/](docs/)

> [!NOTE]
> Dieses Projekt verwendet den MicroPython-Treiber [`dwm3000-micropython`](https://github.com/foldedtoad/dwm3000-micropython), der aus dem ursprünglichen Repository geklont wurde.

---
## Installation

1. MicroPython auf den Pico 2 W flashen (einmalig)

   - **BOOTSEL** gedrückt halten und den Pico per USB einstecken
   - In Thonny rechts unten auf den Interpreter klicken → **Configure interpreter… → MicroPython (Raspberry Pi Pico)**
   - **Install or update MicroPython** klicken und **Raspberry Pi Pico 2 W** auswählen

2. DWM3000EVB mit dem Pico verkabeln

   | DWM3000EVB | Pico 2 W |
   |---|---|
   | SPI CLK | GP18 (Pin 24) |
   | SPI MISO | GP16 (Pin 21) |
   | SPI MOSI | GP19 (Pin 25) |
   | SPI CSn | GP17 (Pin 22) |
   | 3V3 | 3V3 (Pin 36) |
   | GND | GND (z. B. Pin 23) |
   | RSTn, optional | GP9 (Pin 12) |
   | IRQ, optional | GP2 (Pin 4) |
   | WAKEUP, optional | GP3 (Pin 5) |

   **Jumper J1 auf dem EVB auf „Up“** stellen, damit das Modul die 3,3 V vom Pico bekommt.

3. Treiber mit Thonny auf den Pico kopieren

   Folgende Ordner und Dateien müssen ins Hauptverzeichnis `/` des Pico:

   ```
   decadriver/
   platform/
   shared_data/
   config_options.py
   ```

   In Thonny **Ansicht → Dateien** öffnen (oben PC, unten Pico), die vier Einträge mit `Strg`+Klick markieren und mit Rechtsklick → **Hochladen nach /** hochladen.

   Note: Nach Änderungen am Treiber die geänderten Dateien erneut hochladen, da der Pico seine eigene Kopie benutzt.

# Beispiele

Gewünschte `main.py` in Thonny öffnen und mit **Run** (F5) starten. Stoppen mit **Stop** oder `Strg+C`.

1. Verbindung testen

   ```
   examples/util_pin_test/main.py                 Pins und Kabel prüfen (EVB abstecken)
   examples/util_read_dev_id_spi_only/main.py     SPI prüfen, nur SPI-Leitungen nötig
   examples/ex_00a_reading_dev_id/main.py         DEV_ID über den Treiber lesen
   ```

   Erwartete Ausgabe: DEV_ID `0xdeca0302`

2. Senden und Empfangen (muss noch getestet werden)

   ```
   Board 1:  examples/ex_02a_simple_rx/main.py
   Board 2:  examples/ex_01a_simple_tx/main.py
   ```

3. Entfernungsmessung (muss noch getestet werden)

   Den Responder immer zuerst starten.

   ```
   Board 1:  examples/ex_06b_ss_twr_responder/main.py
   Board 2:  examples/ex_06a_ss_twr_initiator/main.py
   ```

   oder (Double-Sided)

   ```
   Board 1:  examples/ex_05b_ds_twr_responder/main.py
   Board 2:  examples/ex_05a_ds_twr_initiator/main.py
   ```

   Note: Die Boards ein paar Minuten warmlaufen lassen, danach wird die Messung deutlich genauer.

Note: Für zwei Boards in Thonny unter **Extras → Optionen → Allgemein** den Haken bei **Nur eine Thonny-Instanz zulassen** entfernen und Thonny zweimal öffnen, je eine Instanz pro Pico (COM-Port im Interpreter-Menü auswählen).

Soll ein Programm beim Einstecken automatisch starten, es über **Datei → Speichern unter… → Raspberry Pi Pico** als `main.py` speichern.

---

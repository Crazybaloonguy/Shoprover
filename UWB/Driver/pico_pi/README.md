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
   | RSTn | GP9 (Pin 12) beim Flexypin, GP7 (Pin 10) beim ArduPico |
   | IRQ, optional | GP2 (Pin 4) |
   | WAKEUP, optional | GP3 (Pin 5) |

   Das verwendete Board in `dw_platform/port.py` einstellen (`BOARD = "flexypin"` oder `"ardupico"`).

   **Jumper J1 auf dem EVB auf „Up“** stellen, damit das Modul die 3,3 V vom Pico bekommt.

3. Treiber mit Thonny auf den Pico kopieren

   Folgende Ordner und Dateien aus `pico_pi/` müssen ins Hauptverzeichnis `/` des Pico:

   ```
   decadriver/
   dw_platform/
   shared_data/
   config_options.py
   commmunication_utils.py
   handshake.py
   main.py
   ```

   In Thonny **Ansicht → Dateien** öffnen (oben PC, unten Pico). Im Ordner `pico_pi/` die sieben Einträge
   mit `Strg`+Klick markieren und mit Rechtsklick → **Hochladen nach /** hochladen.

   Note: `main.py` ist das Tag-Programm (siehe [Tag](#tag)). Der Pico startet es beim Einstecken automatisch.

   Note: Der Ordner hieß früher `platform/`. Liegt auf dem Pico noch ein alter `platform/`-Ordner, kann er gelöscht werden.

   Note: Nach Änderungen am Treiber die geänderten Dateien erneut hochladen, da der Pico seine eigene Kopie benutzt.

# Tag

`main.py` ist das Programm des Tags: Es wartet, bis sich `ANCHOR_COUNT` Anchors (Standard 3) registriert
haben, bestätigt jeden mit einem ACK und speichert ihre Adressen.

Danach sendet es als Test jede Sekunde `Hallo <Adresse>` an jeden Anchor, z. B. `Hallo 0x0002` an
Anchor 0x0002. Jede Nachricht ist nur an diesen einen Anchor adressiert (`TEST_INTERVAL_MS` in `main.py`).

Den Tag zuerst starten (Pico einstecken, oder `main.py` in Thonny öffnen und mit **Run** (F5) starten),
danach die Anchors.

# Beispiele

Die Beispiele zeigen einzelne Funktionen des Treibers. Gewünschte `main.py` in Thonny öffnen und mit
**Run** (F5) starten. Stoppen mit **Stop** oder `Strg+C`.

Die Beispiele liegen in `pico_pi/examples/`. Pfade unten relativ zu `pico_pi/`.

1. Senden und Empfangen

   ```
   Board 1:  examples/ex_02a_simple_rx/main.py
   Board 2:  examples/ex_01a_simple_tx/main.py
   ```

2. Entfernungsmessung (Double-Sided)

   Den Responder immer zuerst starten.

   ```
   Board 1:  examples/ex_05b_ds_twr_responder/main.py
   Board 2:  examples/ex_05a_ds_twr_initiator/main.py
   ```

   Note: Die Boards ein paar Minuten warmlaufen lassen, danach wird die Messung deutlich genauer.

Note: Für zwei Boards in Thonny unter **Extras → Optionen → Allgemein** den Haken bei **Nur eine Thonny-Instanz zulassen** entfernen und Thonny zweimal öffnen, je eine Instanz pro Pico (COM-Port im Interpreter-Menü auswählen).

Soll ein Programm beim Einstecken automatisch starten, es über **Datei → Speichern unter… → Raspberry Pi Pico** als `main.py` speichern.

---

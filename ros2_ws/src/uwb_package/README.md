uwb_package
---

ROS 2 (Jazzy) Paket für die UWB-Anchors (Qorvo DW3000 auf einem DWM3000EVB) am Raspberry Pi 4 mit
Ubuntu 24.04. Der Node initialisiert den DW3000, registriert die Anchors beim Tag (Handshake), beantwortet
danach die Abstandsmessungen des Tags und veröffentlicht Zustand und Abstände.

| Datei / Ordner | Inhalt |
|---|---|
| `uwb_package/uwb_node.py` | Node: DW3000 starten, Anchors beim Tag registrieren |
| `uwb_package/uwb_publisher.py` | Publisher für die UWB-Daten |
| `uwb_package/uwb_driver.py` | Initialisiert den DW3000 für den Node |
| `uwb_package/driver/` | DW3000-Treiber für den Pi |
| `uwb_package/driver/decadriver/` | DW3000-Registertreiber |
| `uwb_package/driver/dw_platform/` | Pi-spezifisch: Pins, SPI, Reset, IRQ |
| `uwb_package/driver/commmunication_utils.py` | Nachrichten senden und empfangen |
| `uwb_package/driver/handshake.py` | Registrierung der Anchors beim Tag |
| `uwb_package/driver/ranging.py` | Abstandsmessung Tag ↔ Anchor (Double-Sided Two-Way Ranging) |
| `uwb_package/examples/` | Testprogramme ohne ROS (Senden, Empfangen, Entfernungsmessung) |
| `launch/uwb.launch.py` | Startet den Node mit seinen Parametern |

Note: Nachrichtenformat (`commmunication_utils.py`), Handshake (`handshake.py`) und Funk-Konfiguration
(`uwb_driver.py`) müssen zum Tag passen.

---
## Einrichtung des Raspberry Pi

1. Pakete installieren

   ```bash
   sudo apt install python3-spidev python3-lgpio
   ```

2. SPI ohne Kernel-Chip-Select aktivieren

   Der Treiber steuert CSn selbst über GPIO8, GPIO7 und GPIO16. Damit der Kernel GPIO8 und GPIO7
   (CE0/CE1) nicht belegt, in `/boot/firmware/config.txt` die Zeile `dtparam=spi=on` auskommentieren
   und am Ende ergänzen:

   ```
   dtoverlay=spi0-0cs
   ```

   Danach neu starten und prüfen:

   ```bash
   ls /dev/spidev0.0                          # muss vorhanden sein
   gpioinfo | grep '"GPIO8"\|"GPIO7"\|"GPIO16"'   # alle drei müssen "unused" zeigen
   ```

   Note: Fehlt `/dev/spidev0.0`, `dtparam=spi=on` wieder einkommentieren und `dtoverlay=spi0-0cs` darunter stehen lassen.

3. Zugriff ohne `sudo`

   Der Benutzer braucht Zugriff auf `/dev/spidev0.0` und `/dev/gpiochip0`:

   ```bash
   ls -l /dev/spidev0.0 /dev/gpiochip0       # Gruppe ablesen, z. B. spi / gpio / dialout
   sudo usermod -aG <gruppe> $USER           # für jede Gruppe, danach neu anmelden
   ```

4. DWM3000EVBs mit dem Pi verkabeln

   Alle Module hängen am selben SPI-Bus und am selben RSTn, jedes hat seinen eigenen CSn:

   | DWM3000EVB | Raspberry Pi 4 |
   |---|---|
   | SPI CLK | GPIO11 (Pin 23), alle Module |
   | SPI MISO | GPIO9 (Pin 21), alle Module |
   | SPI MOSI | GPIO10 (Pin 19), alle Module |
   | SPI CSn | Modul 0: GPIO8 (Pin 24), Modul 1: GPIO7 (Pin 26), Modul 2: GPIO16 (Pin 36) |
   | 3V3 | 3V3 (Pin 1 oder 17), alle Module |
   | GND | GND (z. B. Pin 6), alle Module |
   | RSTn | GPIO25 (Pin 22), alle Module |
   | IRQ, WAKEUP | nicht anschließen (werden nicht gebraucht) |

   **Jumper J1 auf jedem EVB auf „Up“** stellen, damit die Module die 3,3 V vom Pi bekommen.

   Note: Der Treiber fragt das Statusregister ab, statt auf IRQ zu warten. Deshalb wird die IRQ-Leitung nicht gebraucht.

   Note: GPIO-Nummer und Pin-Nummer nicht verwechseln: GPIO25 ist Pin 22, Pin 25 ist GND.

   Andere Verkabelung: `PINS` in `uwb_package/driver/dw_platform/port.py` anpassen.

---
## Bauen und starten

```bash
cd ~/Shoprover/ros2_ws
colcon build --packages-select uwb_package
source install/setup.bash

ros2 launch uwb_package uwb.launch.py
```

Zuerst den Tag starten.

Nach dem Handshake misst der Tag reihum den Abstand zu jedem Anchor (erst Anchor 0, dann 1, dann 2, je
1 ms Pause dazwischen). Jeder Anchor bekommt dabei nur seine eigene Messung, berechnet den Abstand und
gibt ihn aus:

```
[uwb_node]: anchor 0x0002 (DW3000 1): distance to tag 0x0100: 2.97 m
```

Ist eine Messung fehlgeschlagen (z. B. Antwort zu spät), erscheint eine Warnung; die nächste Runde misst neu.

Zustand ansehen:

```bash
ros2 topic echo /uwb/status
ros2 topic echo /uwb/anchors
ros2 topic echo /uwb/goal_coordinate
```

### Topics

| Topic | Typ | Inhalt |
|---|---|---|
| `uwb/status` | `std_msgs/String` | Zustand, z. B. `anchor 0x0001: registered at tag 0x0100`, `ready: …`, `error: …` |
| `uwb/anchors` | `std_msgs/UInt16MultiArray` | Adressen der beim Tag registrierten Anchors |
| `uwb/goal_coordinate` | `geometry_msgs/PointStamped` | Position des Tags in m relativ zum Fahrzeug (`frame_id = base_link`, `point.x` / `point.y`, `z = 0`); einmal pro Runde, sobald jeder Anchor einen neuen Abstand hat |

`uwb/status` und `uwb/anchors` behalten den letzten Wert (transient local), auch später gestartete Nodes bekommen ihn.

Note: Die Antennen-Delays sind noch nicht kalibriert (`TX_ANT_DLY`/`RX_ANT_DLY` in `driver/ranging.py`), die
Abstände haben deshalb einen konstanten Fehler.

### Parameter

| Parameter | Standard | Bedeutung |
|---|---|---|
| `anchor_addresses` | `[1, 2, 3]` (Launch-File) | Adressen der Anchors, eine pro Modul in der Reihenfolge der CSn-Pins: die erste gehört zu Modul 0 (GPIO8), die zweite zu Modul 1 (GPIO7), die dritte zu Modul 2 (GPIO16) |
| `anchor_positions` | siehe Launch-File | Position jedes Anchors in m relativ zum Fahrzeug als flache Liste `[x0, y0, x1, y1, …]`, gleiche Reihenfolge wie `anchor_addresses`; alle Werte als Float (`0.0`, nicht `0`) |

Note: Der Tag muss auf genau so viele Anchors warten, wie `anchor_addresses` Einträge hat.

Note: Mit nur einem angeschlossenen Modul `anchor_addresses: [1]` im Launch-File setzen (und den Tag auf
einen Anchor einstellen). Sonst bricht der Node ab, weil Modul 1 (GPIO7) nicht antwortet.

---
## Testprogramme ohne ROS

Nach `colcon build` und `source install/setup.bash`, stoppen mit `Strg+C`:

```bash
python3 -m uwb_package.examples.ex_02a_simple_rx            # empfängt, Gegenseite muss senden
python3 -m uwb_package.examples.ex_01a_simple_tx            # sendet, Gegenseite muss empfangen
python3 -m uwb_package.examples.ex_05b_ds_twr_responder     # Responder, Gegenseite: Initiator
python3 -m uwb_package.examples.ex_05a_ds_twr_initiator     # Initiator, Gegenseite: Responder
```

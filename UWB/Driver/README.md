DWM3000 Treiber
---

Python-Treiber für den Qorvo DW3000 (UWB) auf dem DWM3000EVB, für zwei Plattformen.
Der Treiber und die Beispiele existieren nur einmal; pro Plattform gibt es nur die Hardware-Schicht.

```
Driver/
  decadriver/          DW3000-Treiber (plattformunabhängig)
  shared_data/         gemeinsame Konstanten und Hilfsfunktionen der Beispiele
  config_options.py    TX-Kalibrierwerte
  examples/            Beispiele, laufen auf Pico und Pi

  pico_pi/             Raspberry Pi Pico 2 W (MicroPython)
    dw_platform/       SPI, GPIO, Reset, IRQ mit machine.Pin/SPI
    examples/          Verkabelungstests (Pico-spezifisch)

  raspberry_pi/        Raspberry Pi 4 (CPython)
    dw_platform/       SPI, GPIO, Reset, IRQ mit spidev/lgpio
    examples/          Verkabelungstests (Pi-spezifisch)
    utime.py           MicroPython-utime-Nachbau
    run.py             startet die Beispiele aus examples/
```

Der gemeinsame Code importiert die Hardware-Schicht immer als `dw_platform` (`from dw_platform.port import port`).
Welche Plattform benutzt wird, entscheidet nur, welcher `dw_platform/`-Ordner im Importpfad liegt:

- **Pico:** gemeinsame Dateien und `pico_pi/dw_platform/` zusammen ins Pico-Hauptverzeichnis hochladen, siehe [pico_pi/README.md](pico_pi/README.md).
- **Raspberry Pi:** `raspberry_pi/run.py` setzt die Pfade, siehe [raspberry_pi/README.md](raspberry_pi/README.md).

Neue Plattform: Ordner mit eigenem `dw_platform/` (`port.py` mit einem `port`-Objekt, `deca_spi.py` mit
`writetospi()`/`readfromspi()`) anlegen. Am gemeinsamen Code ändert sich nichts.

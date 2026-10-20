## Systemarchitektur

### Raspberry Pi - Zentral Steuerung

- LiDAR-Messwerte verarbeiten
- Position der Person anhand der UWB-Daten bestimmen
- Bewegungs- und Lenkvorgaben berechnen
- Hindernisse erkennen und beurteilen, ob eine Bewegung sicher ist
- Bewegungsbefehle an den ESP32 senden

### ESP32 - Motorsteuerung

- Motorgeschwindigkeit und Lenkung steuern
- Bewegungsbefehle des Raspberry Pi ausführen
- Kommunikations-Timeouts und den Zustand der Steuerung überwachen

### ESP32 - UWB
- misst Distanz zum Tag
- übergibt Distanz zum Raspberry Pi
- einer Konfiguert den Tag

## Übersicht Architektur
<img width="1212" height="297" alt="Aufbau" src="https://github.com/user-attachments/assets/8e09414e-35f1-4c4a-bc52-09ea7f960055" />

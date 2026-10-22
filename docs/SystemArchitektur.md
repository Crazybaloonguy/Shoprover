## Systemarchitektur

### Raspberry Pi - Zentral Steuerung

- LiDAR-Messwerte verarbeiten
- Position der Person anhand der UWB-Daten bestimmen
- Bewegungs- und Lenkvorgaben berechnen
- Hindernisse erkennen und beurteilen, ob eine Bewegung sicher ist
- Bewegungsbefehle an den Pi Pico senden

### Pi Pico - Motorsteuerung

- Motorgeschwindigkeit und Lenkung steuern
- Bewegungsbefehle des Raspberry Pi ausführen
- Kommunikations-Timeouts und den Zustand der Steuerung überwachen

### UWB
- misst Distanz zum Tag
- übergibt Distanz zum Raspberry Pi
- einer Konfiguert den Tag

## Übersicht Architektur

```mermaid
flowchart LR
    P1(PICO No.1)
    P2(PICO No.2)
    Transmitter(Transmitter DWM3000EVB)
    Receiver1(Receiver DWM3000EVB)
    Receiver2(Receiver DWM3000EVB)
    Receiver3(Receiver DWM3000EVB)
    Raspberry("`Raspberry Pi 4 (**Master**)`")
    W1(Wheel 1)
    W2(Wheel 2)
    M(Motor Controller)

    subgraph PERSON
        P1 --> Transmitter
    end
    subgraph SHOP ROVER
        subgraph RECEIVER
            Transmitter --> Receiver1
            Transmitter --> Receiver2
            Transmitter --> Receiver3
        end
        subgraph CONTROLLER
            Receiver1 --> Raspberry
            Receiver2 --> Raspberry
            Receiver3 --> Raspberry
            Raspberry --> P2
        end
        subgraph DRIVE UNIT
            P2 --> M
            M --> W1
            M --> W2
        end
    end
```


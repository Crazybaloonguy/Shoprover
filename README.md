# Shoprover - Autonomer Einkaufsroboter

Ein autonomer Einkaufsroboter, der einer Person beim Einkaufen folgt und sie beim Transport von Lebensmitteln und anderen Einkäufen unterstützt.

## Projektziele - Warum?

Der Shoprover soll das Einkaufen einfacher und barrierefreier gestalten, insbesondere für Menschen mit Behinderungen oder eingeschränkter Mobilität.

Der Roboter folgt autonom der ihm zugewiesenen Person, transportiert Einkäufe und erkennt Hindernisse, um sich sicher in seiner Umgebung bewegen zu können.

## Team

- Leonard Schell
- Marcel Kraft 
- Alexej Betz 

## Hardware

- Raspberry Pi (Zentral Steuerung, Sensorverarbeitung und Navigationslogik.)
- Pi Pico (Motorsteuerung)
- LiDAR-Sensor (Hinderniserkennung und Entfernungsmessung)
- [UWB-Sensoren](docs/UWB.md) (Verfolgung der Person sowie Schätzung von Entfernung und Richtung)
- 2x Hoverboard-Motoren (Antrieb des Rovers)
- Motorcontroller (Mit den ausgewählten Hoverboard-Motoren kompatible Steuerungen z.b. VESC)
- E-Bike-Akku (Hauptstromversorgung)
- Spannungsregler und Stromverteilungskomponenten (Zur sicheren Versorgung der einzelnen Komponenten)

## Systemarchitektur

### Raspberry Pi - Zentral Steuerung

- LiDAR-Messwerte verarbeiten
- Position der Person anhand der UWB-Daten bestimmen
- Bewegungs- und Lenkvorgaben berechnen
- Hindernisse erkennen und beurteilen, ob eine Bewegung sicher ist
- Bewegungsbefehle an den Pi Pico senden

### Pi Pico - Motorsteuerung

- Motorgeschwindigkeit und Lenkung steuern
- Bewegungsbefehle des Raspberry Pi ausführen (mit hilfe ros2)
- Kommunikations-Timeouts und den Zustand der Steuerung überwachen

## Sensoren

UWB: Schätzt die Entfernung zur Person und ermöglicht mit einer geeigneten Konfiguration auch die Bestimmung ihrer Richtung oder Position

LiDAR: Erkennt Hindernisse und misst die Entfernungen zu Objekten in der Umgebung

## Kritische Funktionen

### CF1 - Autonomes Folgen einer Person

Beschreibung: Der Shoprover muss der zugewiesenen Person folgen und dabei einen konfigurierbaren Sicherheitsabstand einhalten.

Warum? Der Hauptzweck des Rovers besteht darin, die Person beim Einkaufen zu unterstützen, ohne dass sie den Rover manuell steuern muss.

Akzeptanzkriterien:

- Der zugewiesene UWB-Tag wird erkannt und verfolgt
- Der eingestellte Folgeabstand wird innerhalb einer definierten Toleranz eingehalten
- Wenn die Person nicht mehr zuverlässig lokalisiert werden kann, stoppt der Rover

> [!NOTE] 
> Detailierte Informationen über UWB Technologie finden sie [hier](docs/UWB.md)

### CF2 - Hinderniserkennung und Hindernisvermeidung

Beschreibung: Der Rover muss Hindernisse auf seinem Weg erkennen und anhalten oder ihnen ausweichen, sofern dies möglich ist.

Warum? Dadurch sollen Kollisionen mit Menschen, Einkaufswagen, Regalen und anderen Objekten verhindert werden.

Akzeptanzkriterien:

- Hindernisse werden innerhalb des festgelegten Erfassungsbereichs erkannt
- Der Rover stoppt, bevor er ein Hindernis innerhalb der definierten Erfassungsbereichs erreicht
- Die Bewegung wird erst fortgesetzt, wenn der Weg wieder frei ist

### CF3 - Autonome Bewegung und Lenkung

Beschreibung: Der Rover muss mithilfe der Motorcontroller und des Lenkmechanismus vorwärts- und rückwärtsfahren, anhalten, abbiegen und seine Geschwindigkeit regulieren können.

Warum? Personenverfolgung ist nur dann sinnvoll, wenn der Rover die daraus abgeleiteten Bewegungsbefehle zuverlässig ausführen kann.

Akzeptanzkriterien:

- Vorwärtsfahren, Rückwärtsfahren, Anhalten und Abbiegen werden unterstützt
- Bewegungsbefehle des Raspberry Pi werden ausgeführt
- Der Rover bewegt sich bei der eingestellten Höchstgeschwindigkeit vorhersehbar und kontrollierbar

### CF4 - Ausfallsicherer Betrieb (Fail-Safe)

Beschreibung: Bei kritischen Fehlern muss der Rover in einen Stillstand wechseln.

Warum? Dadurch werden unkontrollierte Bewegungen verhindert, wenn die Kommunikation, Sensorik oder Steuerung ausfällt.

Akzeptanzkriterien:

- Ein Kommunikationsverlust zwischen Raspberry Pi und Pi Pico führt zum Stillstand
- Ein Verlust der zuverlässigen Personenverfolgung führt zum Stillstand

## Aufgaben

### Task 1 - Anforderungen und Systemdesign

- Einsatzumgebung und maximale Geschwindigkeit festlegen
- Zielabstand zur Person und erforderlichen Anhalteweg definieren
- Systemarchitektur entwerfen
- Schnittstellen zwischen Raspberry Pi und Pi Pico festlegen
- Schnittstellen zwischen Pi Pico und Antrieb festlegen

### Task 2 - Fahrgestell und mechanischer Aufbau

- Fahrgestell auswählen und montieren
- Motoranordnung und Lenkmechanismus bestimmen
- Zuladung, Drehmoment und erforderliche Motorleistung bestimmen

### Task 3 - Stromversorgung und Elektronik

- Kompatible Motorcontroller auswählen
- Stromversorgung für Motoren, Raspberry Pi, Pi Pico und Sensoren entwerfen
- Akkuspannung und Strombedarf überprüfen

### Task 4 - Motorsteuerung (Pi Pico)

- Kommunikation mit den Motorcontrollern herstellen
- Geschwindigkeits- und Lenksteuerung implementieren
- Stoppbefehle und Kommunikations-Timeouts implementieren
- Antriebssystem mit sicher angehobenen Rädern testen

### Task 5 - Hinderniserkennung (Raspberry Pi + LiDAR)

- LiDAR anschließen und konfigurieren
- Entfernungsmessungen auslesen und verarbeiten
- Hinderniserkennung implementieren
- Anhalteverhalten mit statischen und beweglichen Hindernissen testen

### Task 6 – Personenverfolgung (UWB)

- Kommunikation zwischen dem UWB-System und dem Raspberry Pi herstellen
- Entfernung zur Person und, sofern unterstützt, deren Richtung oder Position bestimmen
- Regelung des Folgeabstands implementieren
- Zuverlässigkeit der Verfolgung in unterschiedlichen Innenräumen testen

### Task 7 - Tests und Validierung

- Alle Teilsysteme einzeln testen
- Personenverfolgung in einer kontrollierten Umgebung testen
- Hinderniserkennung und Anhalteverhalten überprüfen
- Kommunikationsausfälle und Sensorfehler testen
- Testergebnisse und verbleibende Einschränkungen dokumentieren

## Meilensteine

### Meilenstein 1 - Planung und Systemdesign abgeschlossen

Ergebnis: Die Anforderungen, Systemarchitektur und Komponentenliste sind festgelegt. Die mechanische Konstruktion, die Stromversorgung sowie die Schnittstellen zwischen Raspberry Pi, Pi Pico, Sensoren und Motorcontrollern sind geplant.

### Meilenstein 2 - Grundsystem und Antrieb funktionsfähig

Ergebnis: Das Fahrgestell ist aufgebaut und die Elektronik installiert. Der Rover kann unter Steuerung des Pi Pico vorwärts- und rückwärtsfahren, lenken und sicher anhalten. Die grundlegenden Kommunikationsfunktionen sind implementiert.

### Meilenstein 3 - Autonome Navigation und Personenverfolgung integriert

Ergebnis: Die UWB-Sensoren ermöglichen die Verfolgung einer zugewiesenen Person. Der LiDAR-Sensor erkennt Hindernisse, und der Raspberry Pi verarbeitet die Sensordaten, berechnet Bewegungsbefehle und steuert das Fahrverhalten des Rovers.

### Meilenstein 4 - Gesamtsystem getestet und dokumentiert

Ergebnis: Personenverfolgung, Hinderniserkennung und autonome Bewegung arbeiten zusammen. Die Sicherheitsfunktionen und das Anhalteverhalten wurden in einer kontrollierten Umgebung getestet. Testergebnisse, bekannte Einschränkungen, Betriebsanleitung und vollständige Projektdokumentation liegen vor.

# Raspberry Pi (Setup)

Diese Anleitung beschreibt die Grundinstallation des Raspberry Pi 4 für den Shoprover.

## 1. Betriebssystem installieren

1. **Image herunterladen und flashen**:
   Die MicroSD-Karte mithilfe eines Kartenlesers und dem [Raspberry Pi Imager](https://www.raspberrypi.com/software/) mit **Ubuntu 24.04.5 LTS (64-Bit)** flashen.
2. **Erstkonfiguration**:
   Den Raspberry Pi starten, Tastatur/Bildschirm oder SSH anschließen, eine Netzwerkverbindung (WLAN oder Ethernet) herstellen, Zeitzone setzen und einen Benutzer anlegen.

## 2. ROS 2 Jazzy installieren

Die Installation erfolgt gemäß der offiziellen Anleitung:
- [ROS 2 Jazzy – Installation unter Ubuntu (Debian packages)](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)

Kurzfassung:
```bash
# Locale prüfen
locale

# ROS 2 apt Repository hinzufügen
sudo apt install software-properties-common curl -y
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Pakete installieren
sudo apt update
sudo apt install -y ros-jazzy-ros-base ros-dev-tools
```

## 3. Benötigte Werkzeuge & Treiberpakete

```bash
sudo apt update
sudo apt install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-serial \
    python3-spidev \
    python3-lgpio \
    git build-essential
```

## 4. Berechtigungen & Hardware-Schnittstellen

1. **Serielle Schnittstellen freigeben (Dialout-Gruppe)**:
   ```bash
   sudo usermod -a -G dialout $USER
   ```
2. **SPI für die UWB-Receiver aktivieren**:
   In `/boot/firmware/config.txt` am Ende folgende Zeile ergänzen:
   ```text
   dtoverlay=spi0-0cs
   ```
   Anschließend neu starten:
   ```bash
   sudo reboot
   ```

## 5. Weiterführende Schritte

- Das Kompilieren des ROS 2 Workspaces (`ros2_ws`), das Starten der Nodes und die Verdrahtung mit dem Hoverboard und den Sensoren ist detailliert in der [**Bau- und Flash-Anleitung (docs/Build.md)**](Build.md) beschrieben.

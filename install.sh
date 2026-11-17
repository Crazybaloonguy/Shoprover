#!/bin/bash
# Installiert alle Abhängigkeiten und baut den ROS2-Workspace.
# Aufruf: ./install.sh            (ROS-Distro wird automatisch erkannt)
#         ./install.sh jazzy      (Distro explizit angeben)

set -e  # bei Fehler abbrechen

cd "$(dirname "$0")"   # in den Repo-Ordner wechseln

# --- ROS-Distro bestimmen ---------------------------------------------------
if [ -n "$1" ]; then
    ROS_DISTRO="$1"
elif [ -z "$ROS_DISTRO" ]; then
    ROS_DISTRO="$(ls /opt/ros 2>/dev/null | head -n 1)"
fi

if [ -z "$ROS_DISTRO" ] || [ ! -f "/opt/ros/$ROS_DISTRO/setup.bash" ]; then
    echo "FEHLER: Keine ROS2-Installation unter /opt/ros gefunden."
    exit 1
fi
echo ">>> ROS-Distro: $ROS_DISTRO"

source "/opt/ros/$ROS_DISTRO/setup.bash"

# --- Submodule holen --------------------------------------------------------
echo ">>> Submodule aktualisieren"
git submodule update --init --recursive

# --- Pakete installieren ----------------------------------------------------
echo ">>> apt-Pakete installieren"
sudo apt update
sudo apt install -y \
    ros-dev-tools \
    ros-$ROS_DISTRO-navigation2 \
    ros-$ROS_DISTRO-nav2-bringup \
    ros-$ROS_DISTRO-slam-toolbox \
    ros-$ROS_DISTRO-xacro

# --- rosdep -----------------------------------------------------------------
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    echo ">>> rosdep initialisieren"
    sudo rosdep init
fi
rosdep update

echo ">>> Abhängigkeiten per rosdep installieren"
cd ros2_ws
rosdep install --from-paths src -y --ignore-src --rosdistro "$ROS_DISTRO"

# --- Bauen ------------------------------------------------------------------
echo ">>> Workspace bauen"
colcon build --symlink-install

echo ""
echo ">>> Fertig! Starten mit: ./start.sh"
#!/bin/bash

# Ordner des Skripts = Repo-Root
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$REPO_DIR/ros2_ws"
CONFIG="$WS/src/hoverboard_ros2_control/hoverboard_demo_bringup/config"

# ROS-Umgebung laden
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

source "$WS/install/setup.bash"

# Beim Beenden (Strg+C oder systemctl stop) alle Launches sauber mitbeenden
trap "kill -INT 0" SIGINT SIGTERM

ros2 launch rplidar_ros rplidar.launch.py &
sleep 3

ros2 launch hoverboard_demo_bringup hoverboard.launch.py &
sleep 5

ros2 launch slam_toolbox online_async_launch.py \
    use_sim_time:=false \
    slam_params_file:="$CONFIG/mapper_params_online_async.yaml" &
sleep 5

ros2 launch nav2_bringup navigation_launch.py \
    use_sim_time:=false \
    params_file:="$CONFIG/nav2.yaml" &

wait
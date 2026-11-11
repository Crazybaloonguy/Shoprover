"""
Starts the UWB node: initialises the DW3000 and registers the anchors at
the tag. Start the tag first.

    ros2 launch uwb_package uwb.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            name='uwb_node',
            package='uwb_package',
            executable='uwb_node',
            output='screen',
            parameters=[{
                # One address per DW3000, in the order of the CS pins in
                # driver/dw_platform/port.py (GPIO8, GPIO7, GPIO16). The tag
                # must wait for as many anchors.
                'anchor_addresses': [1, 2, 3],
                'anchor_positions': [0.45, 0.0,   -0.5, 0.5,   -0.5, -0.5],   # x0,y0, x1,y1, x2,y2
            }],
        ),
    ])

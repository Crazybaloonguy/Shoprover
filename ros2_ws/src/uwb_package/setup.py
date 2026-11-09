from setuptools import find_packages, setup

package_name = 'uwb_package'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/uwb.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Leonard Schell',
    maintainer_email='lschell@stud.hs-heilbronn.de',
    description='UWB anchors (DW3000) on the Raspberry Pi',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'uwb_node = uwb_package.uwb_node:main'
        ],
    },
)

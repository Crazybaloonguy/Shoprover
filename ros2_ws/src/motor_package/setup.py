from setuptools import find_packages, setup

package_name = 'motor_package'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='marcel',
    maintainer_email='marcel.kraft3@web.de',
    description='Motor control package controls hoverboard motors',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'motor_node = motor_package.motor_node:main'
        ],
    },
)

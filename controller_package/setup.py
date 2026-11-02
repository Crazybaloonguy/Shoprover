from setuptools import find_packages, setup

package_name = 'controller_package'

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
    description='TODO: Package description',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'controller_node = controller_package.controller_node:main',
            'talker = controller_package.publisher_member_function:main',
            'listener = controller_package.subscriber_member_function:main',
        ],
    },
)

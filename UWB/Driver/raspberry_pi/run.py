"""
raspberry_pi/run.py

Starts a shared example (Driver/examples/) on the Raspberry Pi. On the Pico,
everything is copied into one filesystem root; here the shared code
(Driver/) and this platform's files (raspberry_pi/: dw_platform, utime.py)
stay in their folders, so this puts both on sys.path and then runs the
example as __main__.

Usage (from anywhere):
    python3 raspberry_pi/run.py ex_00a_reading_dev_id
    python3 raspberry_pi/run.py examples/ex_00a_reading_dev_id/main.py
"""

import os
import runpy
import sys

PLATFORM_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVER_DIR = os.path.dirname(PLATFORM_DIR)
EXAMPLES_DIR = os.path.join(DRIVER_DIR, "examples")


def resolve(arg):
    """Accept an example name or a path to its main.py / folder."""
    for path in (arg, os.path.join(EXAMPLES_DIR, arg)):
        if os.path.isdir(path):
            path = os.path.join(path, "main.py")
        if os.path.isfile(path):
            return os.path.abspath(path)
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        print()
        print("Examples:")
        for name in sorted(os.listdir(EXAMPLES_DIR)):
            print("  " + name)
        sys.exit(1)

    script = resolve(sys.argv[1])
    if script is None:
        sys.exit("example not found: %s" % sys.argv[1])

    # Platform first, so its dw_platform/utime win over anything else.
    sys.path[:0] = [PLATFORM_DIR, DRIVER_DIR]
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()

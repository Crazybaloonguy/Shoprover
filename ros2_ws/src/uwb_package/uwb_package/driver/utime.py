"""
utime.py

CPython stand-in for the MicroPython `utime` module, which decadriver and
the examples use (`from .. import utime as time`).
Only the functions this project uses are provided.

Ticks come from a monotonic clock and never wrap here, but ticks_diff() /
ticks_add() are kept so code written for MicroPython's wrapping ticks still
reads the same.
"""

import time as _time

sleep = _time.sleep


def sleep_ms(ms):
    _time.sleep(ms / 1000)


def sleep_us(us):
    # Linux sleeps carry ~50-100 us of overhead, so very short delays spin.
    if us < 200:
        end = _time.perf_counter_ns() + us * 1000
        while _time.perf_counter_ns() < end:
            pass
    else:
        _time.sleep(us / 1_000_000)


def ticks_ms():
    return _time.monotonic_ns() // 1_000_000


def ticks_us():
    return _time.monotonic_ns() // 1_000


def ticks_diff(new, old):
    return new - old


def ticks_add(ticks, delta):
    return ticks + delta

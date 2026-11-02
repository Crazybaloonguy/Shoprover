"""
dw_platform/deca_spi.py

Low-level SPI primitives for the DW3000, Raspberry Pi (spidev) equivalent of
platform/deca_spi.c's openspi()/writetospi()/readfromspi(). decadriver
(target-independent) calls these two functions; only this file and
port.py know about real hardware.

The DW3000 SPI protocol is: assert CS, clock out a 1-3 byte header that
encodes register-file/offset/R-W, then clock the data body in the same
CS-asserted transaction, then release CS. Both functions below take a
pre-built header buffer -- header construction (which varies by register
file/offset per the DW3000 SPI spec) lives in decadriver/deca_device.py,
matching the upstream project's split between "build the header" (target
independent) and "shove bytes over the wire" (target specific).

spidev's xfer2() keeps CE0 asserted for the whole call, so header and body
go out as one list. With port.cs set (see PINS in port.py), CSn is a plain
GPIO lowered and raised around each xfer2() instead, because some kernels
do not release CE0 between back-to-back transfers. Each transaction holds
port.lock, so the IRQ callback
thread cannot run dwt_isr in the middle of it.
"""

from dw_platform.port import port


def writetospi(header: bytes, body: bytes) -> None:
    """
    Write `header` immediately followed by `body` in a single SPI
    transaction (CS held low across both).
    """
    with port.lock:
        if port.cs is not None:
            port.cs.value(0)
        try:
            port.spi.xfer2(list(header) + list(body or b""))
        finally:
            if port.cs is not None:
                port.cs.value(1)


def readfromspi(header: bytes, readlength: int) -> bytes:
    """
    Write `header`, then clock in `readlength` bytes, CS held low across
    both. Returns the bytes read (NOT including the header).
    """
    with port.lock:
        if port.cs is not None:
            port.cs.value(0)
        try:
            rx = port.spi.xfer2(list(header) + [0] * readlength)
        finally:
            if port.cs is not None:
                port.cs.value(1)
    return bytes(rx[len(header):])

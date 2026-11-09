"""
Start-up of the DW3000 devices for the node, and receiving on all of them.

The driver itself is the subpackage uwb_package.driver. Importing its
dw_platform opens SPI and the GPIOs, so it is only imported in
init_dw3000(), once the node is running.

The devices share SPI0 and RSTn and differ only in CSn (PINS in
driver/dw_platform/port.py); device i is the one on the i-th CS pin.
"""

import time

_dwt = None         # driver.decadriver.deca_device, once init_dw3000() has run
_port = None
_count = 0
_listening = set()  # devices whose receiver receive_msg() has turned on


def select_device(index):
    """Point the driver (SPI chip select and local data) at device `index`."""
    _port.select(index)
    _dwt.dwt_setlocaldataptr(index)


def init_dw3000(count):
    """
    Reset all devices, then initialise and configure devices 0 .. count-1,
    as the driver's examples do for one. The configuration must match the
    tag.
    """
    global _dwt, _port, _count
    from uwb_package.driver.dw_platform.port import port
    from uwb_package.driver.decadriver import deca_device as dwt
    from uwb_package.driver.decadriver import deca_regs as R
    from uwb_package.driver.decadriver.deca_types import DwtConfig
    from uwb_package.driver.config_options import txconfig_options

    if count > port.device_count:
        raise RuntimeError('%d anchors, but only %d CS pins in dw_platform/port.py'
                           % (count, port.device_count))

    config = DwtConfig(
        chan=5,
        txPreambLength=R.DWT_PLEN_128,
        rxPAC=R.DWT_PAC8,
        txCode=9,
        rxCode=9,
        sfdType=1,                 # non-standard 8 symbol SFD
        dataRate=R.DWT_BR_6M8,
        phrMode=R.DWT_PHRMODE_STD,
        phrRate=R.DWT_PHRRATE_STD,
        sfdTO=(129 + 8 - 8),
        stsMode=R.DWT_STS_MODE_OFF,
        stsLength=R.DWT_STS_LEN_64,
        pdoaMode=R.DWT_PDOA_M0,
    )

    _dwt, _port = dwt, port

    port.spi_set_rate_high()
    port.reset_dwic()       # shared RSTn: resets all devices at once
    time.sleep(0.002)       # INIT_RC -> IDLE_RC

    for index in range(count):
        select_device(index)
        name = 'DW3000 %d (CSn GPIO%d)' % (index, port.cs.gpio)

        t_end = time.monotonic() + 1.0
        while not dwt.dwt_checkidlerc():
            if time.monotonic() > t_end:
                raise RuntimeError('%s does not reach IDLE_RC (check wiring, RSTn, SPI)' % name)

        if dwt.dwt_initialise(R.DWT_DW_INIT) == R.DWT_ERROR:
            raise RuntimeError('%s: dwt_initialise failed' % name)
        if dwt.dwt_configure(config):
            raise RuntimeError('%s: dwt_configure failed' % name)

        dwt.dwt_configuretxrf(txconfig_options)
        dwt.dwt_setleds(R.DWT_LEDS_ENABLE | R.DWT_LEDS_INIT_BLINK)
        _count = index + 1

    select_device(0)
    _listening.clear()


def receive_msg(addresses, stop):
    """
    Listen on devices 0 .. len(addresses)-1 at once until one of them gets a
    message for its anchor address addresses[i] (or BROADCAST). Every device
    hears every frame, but only the addressed one takes it; the others drop
    it and listen again.

    Returns (device, (code, src, dest, payload)), or None once the
    threading.Event `stop` is set. The other devices keep listening, so
    nothing is missed between two calls.
    """
    from uwb_package.driver import commmunication_utils as cu

    while not stop.is_set():
        for index, addr in enumerate(addresses):
            select_device(index)
            if index not in _listening:
                cu.rx_start()
                _listening.add(index)
                continue

            data = cu.rx_poll()
            if data is None:
                continue
            _listening.discard(index)   # the receiver is off after a frame
            msg = cu.parse_msg(data, addr)
            if msg is not None:
                return index, msg
    return None


def shutdown():
    """Turn the transceivers off (of the devices initialised so far)."""
    for index in range(_count):
        select_device(index)
        _dwt.dwt_forcetrxoff()
    _listening.clear()

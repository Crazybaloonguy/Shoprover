"""
Start-up of the DW3000 devices for the node, and receiving and ranging on
all of them.

The driver itself is the subpackage uwb_package.driver. Importing its
dw_platform opens SPI and the GPIOs, so it is only imported in
init_dw3000(), once the node is running.

The devices share SPI0 and RSTn and differ only in CSn (PINS in
driver/dw_platform/port.py); device i is the one on the i-th CS pin.
"""

import queue
import threading
import time

_dwt = None         # driver.decadriver.deca_device, once init_dw3000() has run
_port = None
_count = 0
_listener = None    # _Listener started by receive_event()


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
    from uwb_package.driver import ranging

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
        ranging.set_antenna_delays()
        dwt.dwt_setleds(R.DWT_LEDS_ENABLE | R.DWT_LEDS_INIT_BLINK)
        _count = index + 1

    select_device(0)


class _Listener(threading.Thread):
    """
    Keeps the receivers of devices 0 .. len(addresses)-1 on and queues what
    each of them gets for its anchor address (see receive_event()). A POLL
    is answered right here (ranging.respond), since the response has to go
    out at a fixed time after it; the resulting distance is queued.

    A DW3000's receiver is off after every frame, also after one for another
    anchor, so every device hears a frame but must listen again right after
    it. This thread does nothing else: if the caller handled a message here
    (e.g. logged it), a frame arriving meanwhile, like the next anchor's
    poll, would find all receivers off and be lost.

    While one device answers a poll (one DS-TWR exchange, ~35 ms), the
    others are not looked after; the tag ranges one anchor at a time.
    """

    def __init__(self, addresses):
        super().__init__(daemon=True)
        self.addresses = list(addresses)
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.error = None

    def run(self):
        from uwb_package.driver import commmunication_utils as cu
        from uwb_package.driver import ranging
        try:
            for index in range(len(self.addresses)):
                select_device(index)
                cu.rx_start()
            while not self.stop.is_set():
                for index, addr in enumerate(self.addresses):
                    select_device(index)
                    data = cu.rx_poll()
                    if data is None:
                        continue            # still listening
                    msg = cu.parse_msg(data, addr)
                    if msg is not None and msg[0] == cu.MSG_POLL and msg[2] == addr:
                        distance = ranging.respond(addr, msg[1])
                        self.messages.put(('range', index, msg[1], distance))
                    elif msg is not None:
                        self.messages.put(('msg', index, msg))
                    cu.rx_start()           # listen again
        except Exception as e:
            self.error = e


def receive_event(addresses, stop):
    """
    Listen on devices 0 .. len(addresses)-1 at once until one of them gets
    something for its anchor address addresses[i]. Every device hears every
    frame, but only the addressed one takes it. Returns one of

        ('range', device, tag_addr, distance)   the tag ranged this anchor;
                                                distance in m, None if the
                                                exchange failed
        ('msg', device, (code, src, dest, payload))   any other message for
                                                this anchor (or BROADCAST)

    or None once the threading.Event `stop` is set. The devices keep
    listening between calls (in a background thread, see _Listener), so
    nothing is missed while the caller handles one; shutdown() stops that.
    """
    global _listener
    if _listener is None or _listener.addresses != list(addresses):
        _stop_listener()
        _listener = _Listener(addresses)
        _listener.start()

    while not stop.is_set():
        if _listener.error is not None:
            raise RuntimeError('receiving failed: %s' % _listener.error)
        try:
            return _listener.messages.get(timeout=0.1)
        except queue.Empty:
            pass
    return None


def _stop_listener():
    global _listener
    if _listener is not None:
        _listener.stop.set()
        _listener.join(timeout=1.0)
        _listener = None


def shutdown():
    """Stop receiving and turn the transceivers off (of the devices initialised so far)."""
    _stop_listener()
    for index in range(_count):
        select_device(index)
        _dwt.dwt_forcetrxoff()

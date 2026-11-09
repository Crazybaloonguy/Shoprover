"""
dw_platform/port.py

Raspberry Pi 4 (Ubuntu 24.04, CPython) I/O for the DWM3000EVB. Equivalent of
the upstream project's platform/port.c -- GPIO setup, reset control, IRQ
dispatch and SPI device handling -- exposed as the `port` object that
decadriver and the examples use.

This is the ONLY file that should need editing for a different wiring.

The package is called dw_platform (not "platform" as upstream) because
CPython already has a standard-library module named `platform`.

Requirements (see README.md for details):
    /boot/firmware/config.txt:  dtoverlay=spi0-0cs   (then reboot)
    sudo apt install python3-spidev python3-lgpio

Several DW3000 share SPI0 (SCLK/MOSI/MISO) and RSTn; each has its own CSn.
select() picks the device the following SPI transactions go to; together
with deca_device.dwt_setlocaldataptr() (same index) it switches the whole
driver to that device. Device 0 is selected at start, so single-device
code needs neither.

Hardware/OS notes:
  - SPI goes through the kernel's spidev driver (/dev/spidev0.0). Chip
    select is a plain GPIO driven by this driver around every transaction,
    (see "cs" in PINS for why not the kernel's CE0/CE1).
  - GPIO goes through lgpio (/dev/gpiochip0). IRQ edges are delivered on
    lgpio's callback *thread*, not as a MicroPython soft IRQ, so a
    re-entrant lock (`port.lock`) keeps SPI transactions atomic and stops
    the ISR from interleaving with one.
"""

import atexit
import os
import tempfile
import threading

# lgpio creates its notification pipes (.lgd-nfy*) for IRQ callbacks in its
# working directory, which defaults to the current directory: that fails in
# read-only directories and leaves root-owned files behind under sudo.
os.environ.setdefault("LG_WD", tempfile.gettempdir())

import lgpio
import spidev
from .. import utime as time

# ---------------------------------------------------------------------------
# Pin assignment (BCM GPIO numbers) -- edit this dict if your wiring differs.
#
#   DWM3000EVB    Pi 4 header
#   SPI CLK   ->  GPIO11 (pin 23)   SPI0 SCLK, all devices
#   SPI MISO  ->  GPIO9  (pin 21)   SPI0 MISO, all devices
#   SPI MOSI  ->  GPIO10 (pin 19)   SPI0 MOSI, all devices
#   SPI CSn   ->  GPIO8  (pin 24)   device 0, driven by this driver (see "cs" below)
#                 GPIO7  (pin 26)   device 1
#                 GPIO16 (pin 36)   device 2
#   RSTn      ->  GPIO25 (pin 22)   all devices
#   IRQ, WAKEUP: not wired (the driver polls the status register). If wired,
#   only for a single device: the IRQ handler does not switch devices.
#
# Chip select: on some kernels (seen on Ubuntu) the SPI driver does not
# release CE0 between back-to-back transfers, so the DW3000 sees one endless
# transfer. This driver therefore raises/lowers CSn itself around every
# transfer. GPIO8 and GPIO7 (CE0/CE1) are only free for
# that with dtoverlay=spi0-0cs (the SPI driver then claims no CS pin at all).
# ---------------------------------------------------------------------------
PINS = {
    "spi_bus":  0,          # /dev/spidev<bus>.<cs>
    "spi_cs":   0,
    "cs":       [8, 7, 16], # DW3000 CSn per device (index = device), driven by hand
    "gpiochip": 0,          # Pi 4 header GPIOs are on /dev/gpiochip0
    "rst":      25,         # DW3000 RSTn, shared -- open-drain (by hand), active low
    "irq":      None,       # DW3000 IRQ -> host (None = not wired)
    "wakeup":   None,       # DW3000 WAKEUP (None = not wired)
}

# SPI clock speeds. The DW3000 requires a slow SPI clock (<3 MHz) until
# dwt_initialise() has completed (it reads OTP/tuning values at low speed),
# then can be run fast (~20-38 MHz depending on IC state) afterward. The Pi 4
# rounds these down to core_clk / (even divider).
SPI_SLOW_HZ = 2_000_000
SPI_FAST_HZ = 16_000_000

# Safety valve for the interrupt servicing loop (see Port.service_irq).
_ISR_MAX_PASSES = 16


class Line:
    """
    One claimed GPIO, with a machine.Pin-style value().
    """

    def __init__(self, handle, gpio):
        self._h = handle
        self.gpio = gpio

    def value(self, v=None):
        if v is None:
            return lgpio.gpio_read(self._h, self.gpio)
        lgpio.gpio_write(self._h, self.gpio, 1 if v else 0)


class Port:
    """
    Owns the SPI device and GPIO lines for the DW3000 devices on the bus.
    Equivalent of the global state set up by platform/port.c's port_init()
    style functions in the upstream project.
    """

    def __init__(self, pins=None):
        self.pins = pins or PINS

        # --- SPI device, opened slow initially (matches deca_spi.c openspi()) ---
        self.spi = spidev.SpiDev()
        self.spi.open(self.pins["spi_bus"], self.pins["spi_cs"])
        self.spi.mode = 0
        self.spi.bits_per_word = 8
        self.spi.max_speed_hz = SPI_SLOW_HZ

        # Held for every SPI transaction and for a whole ISR pass. Re-entrant,
        # because the ISR's own register accesses take it again.
        self.lock = threading.RLock()

        self._h = lgpio.gpiochip_open(self.pins["gpiochip"])

        # --- chip select by hand (active low, idle high), one per device, see
        #     PINS. All idle high, so only the selected device drives MISO. ---
        self.cs_lines = []
        for gpio in self.pins["cs"]:
            try:
                lgpio.gpio_claim_output(self._h, gpio, 1)
            except lgpio.error as e:
                raise RuntimeError("CS GPIO%d not usable (%s) -- is dtoverlay=spi0-0cs set in "
                                   "/boot/firmware/config.txt? (see README.md)" % (gpio, e))
            self.cs_lines.append(Line(self._h, gpio))
        self.selected = 0
        self.cs = self.cs_lines[0]      # CSn of the selected device, used by deca_spi

        # --- reset line: open-drain behaviour done by hand:
        #     "asserting reset" = output low, "released" = input. The Pi's
        #     pull-up keeps the line clearly high when released: the DW3000's
        #     own pull-up is weak, and a pull-down (the default on GPIO25
        #     after boot) holds it in reset. As an input the line also reads
        #     back the real level, see rst.value(). ---
        lgpio.gpio_claim_input(self._h, self.pins["rst"], lgpio.SET_PULL_UP)
        self.rst = Line(self._h, self.pins["rst"])

        # --- IRQ from DW3000 ---
        # The DW3000 drives this line push-pull (active high); the pull-down
        # only stops it floating (and raising phantom interrupts) if the
        # module is absent.
        self.irq = None
        if self.pins["irq"] is not None:
            lgpio.gpio_claim_input(self._h, self.pins["irq"], lgpio.SET_PULL_DOWN)
            self.irq = Line(self._h, self.pins["irq"])

        # --- interrupt dispatch state (see set_dwic_isr) ---
        self.isr_overruns = 0       # times the line was still high after the pass limit
        self._isr = None
        self._irq_cb = None

        # --- WAKEUP line to DW3000 ---
        self.wakeup = None
        if self.pins["wakeup"] is not None:
            lgpio.gpio_claim_output(self._h, self.pins["wakeup"], 0)
            self.wakeup = Line(self._h, self.pins["wakeup"])

    # -----------------------------------------------------------------
    # Device selection
    # -----------------------------------------------------------------
    @property
    def device_count(self):
        return len(self.cs_lines)

    def select(self, index):
        """
        Send the following SPI transactions to device `index` (its CSn).
        Call deca_device.dwt_setlocaldataptr(index) as well, so the driver
        uses that device's local data.
        """
        if not 0 <= index < len(self.cs_lines):
            raise ValueError("no DW3000 device %d (PINS has %d CS pins)" % (index, len(self.cs_lines)))
        with self.lock:     # never switch in the middle of a transaction
            self.selected = index
            self.cs = self.cs_lines[index]

    # -----------------------------------------------------------------
    # SPI speed control -- decadriver calls this after dwt_initialise()
    # -----------------------------------------------------------------
    def spi_set_rate_low(self):
        self.spi.max_speed_hz = SPI_SLOW_HZ

    def spi_set_rate_high(self):
        self.spi.max_speed_hz = SPI_FAST_HZ

    # -----------------------------------------------------------------
    # Reset -- equivalent of reset_DWIC() in the upstream examples
    # -----------------------------------------------------------------
    def reset_dwic(self):
        """
        Hard-reset the DW3000. Open-drain drive low, hold briefly, release,
        then wait for the IC to complete its internal boot/OTP-load sequence.
        RSTn is shared, so this resets all devices.
        """
        rst = self.pins["rst"]
        lgpio.gpio_free(self._h, rst)
        lgpio.gpio_claim_output(self._h, rst, 0)
        time.sleep_ms(2)
        lgpio.gpio_free(self._h, rst)
        lgpio.gpio_claim_input(self._h, rst, lgpio.SET_PULL_UP)  # release
        time.sleep_ms(2)   # allow DW3000 internal boot to complete

    # -----------------------------------------------------------------
    # IRQ handling -- equivalent of port_set_dwic_isr() in upstream port.c
    # -----------------------------------------------------------------
    def set_dwic_isr(self, handler):
        """
        Install `handler` (normally decadriver's dwt_isr) to run whenever the
        DW3000 raises its IRQ line (rising edge, as upstream).

        `handler` runs on lgpio's callback thread, under `self.lock`, so it
        never splits a main-thread SPI transaction. Callbacks it calls (the
        examples' rx_ok_cb etc.) run on that thread too.
        """
        if self.irq is None:
            raise RuntimeError("IRQ pin not defined (see dw_platform/port.py)")
        self.clear_dwic_isr()
        self._isr = handler
        gpio = self.pins["irq"]
        # Re-claim the line (claimed as plain input in __init__) for edge alerts.
        lgpio.gpio_free(self._h, gpio)
        lgpio.gpio_claim_alert(self._h, gpio, lgpio.RISING_EDGE, lgpio.SET_PULL_DOWN)
        self._irq_cb = lgpio.callback(self._h, gpio, lgpio.RISING_EDGE, self._irq_entry)
        # An edge that came before the callback was registered is lost; the
        # line may already be high.
        if self.irq.value():
            self.service_irq()

    def clear_dwic_isr(self):
        """Stop calling the handler (e.g. on exit)."""
        if self._irq_cb is not None:
            self._irq_cb.cancel()
            self._irq_cb = None
        self._isr = None

    def _irq_entry(self, chip, gpio, level, timestamp):
        self.service_irq()

    def service_irq(self):
        """
        Run the installed handler. Repeats while the IRQ line is still high:
        the line is level-like (it stays high while any enabled event is
        pending), so an event that arrives while the handler is already
        running produces no fresh edge to trigger on.
        """
        with self.lock:
            if self._isr is None:
                return
            for _ in range(_ISR_MAX_PASSES):
                self._isr()
                if not self.irq.value():
                    return
            self.isr_overruns += 1  # still asserted after the limit

    def wakeup_pulse(self):
        """Pulse WAKEUP to bring the DW3000 out of low-power sleep."""
        if self.wakeup is None:
            raise RuntimeError("WAKEUP pin not defined (see dw_platform/port.py)")
        self.wakeup.value(1)
        time.sleep_us(500)
        self.wakeup.value(0)

    def close(self):
        """Release the SPI device and GPIO lines. Registered with atexit."""
        if self._h is None:
            return
        self.clear_dwic_isr()
        self.spi.close()
        lgpio.gpiochip_close(self._h)
        self._h = None


# Module-level singleton, mirroring the global state pattern of the upstream
# C examples; it serves all DW3000 devices on the bus (see select()).
port = Port()
atexit.register(port.close)

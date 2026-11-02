"""
dw_platform/port.py

Raspberry Pi 4 (Linux, CPython) I/O for the DWM3000EVB. Equivalent of the
upstream project's platform/port.c -- GPIO setup, reset control, IRQ
dispatch and SPI device handling -- and the Pi twin of the Pico driver's
dw_platform/port.py. It exposes the same `port` object API, so the shared
decadriver and examples (in Driver/) run unchanged.

This is the ONLY file that should need editing for a different wiring.

The package is called dw_platform (not "platform" as upstream) because
CPython already has a standard-library module named `platform`.

Requirements (Ubuntu for Raspberry Pi; see README.md for details):
    dtparam=spi=on in /boot/firmware/config.txt, then reboot
    sudo apt install python3-spidev python3-lgpio

Hardware/OS differences from the Pico version:
  - SPI goes through the kernel's spidev driver (/dev/spidev0.0). Chip
    select is the hardware CE0 line: one xfer2() call keeps it asserted
    across header + body, so no manually driven CS pin is needed.
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
import utime as time

# ---------------------------------------------------------------------------
# Pin assignment (BCM GPIO numbers) -- edit this dict if your wiring differs.
#
#   DWM3000EVB    Pi 4 header
#   SPI CLK   ->  GPIO11 (pin 23)   SPI0 SCLK
#   SPI MISO  ->  GPIO9  (pin 21)   SPI0 MISO
#   SPI MOSI  ->  GPIO10 (pin 19)   SPI0 MOSI
#   SPI CSn   ->  GPIO8  (pin 24)   SPI0 CE0 (driven by the kernel)
#   RSTn      ->  GPIO25 (pin 22)
#   IRQ       ->  GPIO24 (pin 18)
#   WAKEUP    ->  GPIO23 (pin 16)
# ---------------------------------------------------------------------------
PINS = {
    "spi_bus":  0,      # /dev/spidev<bus>.<cs>
    "spi_cs":   0,      # CE0
    "gpiochip": 0,      # Pi 4 header GPIOs are on /dev/gpiochip0
    "rst":      25,     # DW3000 RSTn -- open-drain, active low
    "irq":      24,     # DW3000 IRQ -> host (None = not wired)
    "wakeup":   23,     # DW3000 WAKEUP (None = not wired)
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
    One claimed GPIO, with the machine.Pin-style value() the Pico code uses.
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
    Owns the SPI device and GPIO lines for one DW3000 device.
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

        # --- reset line: open-drain, so writing 1 releases it and the
        #     external pull-up takes it high; writing 0 asserts reset ---
        lgpio.gpio_claim_output(self._h, self.pins["rst"], 1, lgpio.SET_OPEN_DRAIN)
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
        """
        self.rst.value(0)
        time.sleep_ms(2)
        self.rst.value(1)  # release -> pulled high externally
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


# Module-level singleton, mirroring the single-device global state pattern
# used throughout the upstream C examples (one DW3000 per host in all
# ported examples so far).
port = Port()
atexit.register(port.close)

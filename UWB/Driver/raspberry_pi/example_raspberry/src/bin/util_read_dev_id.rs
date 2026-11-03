/*
	Diagnose: prueft SPI, CS und Reset, bevor init() aufgerufen wird.
	init() wartet ohne Timeout auf RCINIT und haengt still, wenn SPI nur Nullen liefert.

	Erwartet: DEV_ID = 0xDECA0302 (oder 0xDECA0312), RCINIT = 1, SPIRDY = 1
	0x00000000 -> MISO/CLK/CS nicht verbunden, Modul ohne Strom oder im Reset
	0xFFFFFFFF -> MISO haengt auf High (Kabel, falscher Pin)

	Start: cargo run --release --bin util_read_dev_id
*/
use rppal::gpio::{Gpio, Mode as GpioMode};
use rppal::spi::{Bus, Mode, SlaveSelect, Spi};

use std::thread;
use std::time::Duration;

use dw3000::ll;

fn main() {
	let mut spi = Spi::new(Bus::Spi0, SlaveSelect::Ss0, 1_000_000, Mode::Mode0)
		.expect("Failed to configure the spi");
	let gpio = Gpio::new().expect("Failed to configure GPIO");
	let mut cs = gpio.get(8).expect("Failed to set up CS PIN").into_output();
	cs.set_high();

	// Pegel von RSTn vor dem Reset (sollte 1 sein, interner Pull-up)
	let mut reset = gpio.get(25).expect("Failed to set up RESET PIN").into_io(GpioMode::Input);
	println!("RSTn (GPIO25) vor Reset: {}", if reset.is_high() { "High" } else { "Low" });

	reset.set_mode(GpioMode::Output);
	reset.set_low();
	thread::sleep(Duration::from_millis(2));
	reset.set_mode(GpioMode::Input);
	thread::sleep(Duration::from_millis(10));
	println!("RSTn (GPIO25) nach Reset: {}", if reset.is_high() { "High" } else { "Low" });

	// 1) Roh-Lesen von DEV_ID ohne Treiber: Header 0x00 + 4 Dummy-Bytes
	let mut buf = [0u8; 5];
	cs.set_low();
	spi.transfer(&mut buf, &[0u8; 5]).expect("SPI transfer failed");
	cs.set_high();
	let raw = u32::from_le_bytes([buf[1], buf[2], buf[3], buf[4]]);
	println!("Roh-SPI  DEV_ID = 0x{:08X}  (Bytes: {:02X?})", raw, buf);

	// 2) Ueber den Low-Level-Treiber
	let mut dw = ll::DW3000::new(spi, cs);
	let id = dw.dev_id().read().expect("dev_id read failed");
	println!(
		"Treiber  DEV_ID = 0x{:04X}{:02X}{:X}{:X}",
		id.ridtag(), id.model(), id.ver(), id.rev()
	);

	// 3) Statusbits, auf die init() wartet
	for _ in 0..5 {
		let st = dw.sys_status().read().expect("sys_status read failed");
		println!("SYS_STATUS: RCINIT={} SPIRDY={} CPLOCK={}", st.rcinit(), st.spirdy(), st.cplock());
		thread::sleep(Duration::from_millis(200));
	}
}

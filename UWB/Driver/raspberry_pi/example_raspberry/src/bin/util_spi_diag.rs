/*
	SPI-Diagnose: liest DEV_ID (0xDECA0302) in mehreren Varianten, um
	einzugrenzen, warum der DW3000 am Pi nur Nullen liefert.

	A  Basis:         1 MHz, Mode0, CS manuell (wie der Treiber)
	B  MISO Pull-up:  wie A, aber mit internem Pull-up an MISO (GPIO9)
	                  -> FF  = MISO floatet, Chip treibt die Leitung gar nicht
	                  -> 00  = etwas zieht MISO aktiv auf Low
	C  Langsam:       100 kHz
	D  Kernel-CS:     CS nicht von Hand schalten, nur der Kernel toggelt GPIO8
	E  SPI Mode3

	Start: cargo build --release --bin util_spi_diag
	       sudo ../target/release/util_spi_diag
*/
use rppal::gpio::{Gpio, Level, Mode as GpioMode, OutputPin, PullUpDown};
use rppal::spi::{Bus, Mode, SlaveSelect, Spi};

use std::thread;
use std::time::Duration;

const TX: [u8; 5] = [0x00, 0xA5, 0x5A, 0xA5, 0x5A];

fn read_dev_id(spi: &mut Spi, cs: &mut OutputPin, manual_cs: bool) -> [u8; 5] {
	let mut rx = [0u8; 5];
	if manual_cs {
		cs.set_low();
	}
	spi.transfer(&mut rx, &TX).expect("SPI transfer failed");
	if manual_cs {
		cs.set_high();
	}
	rx
}

fn show(name: &str, spi: &mut Spi, cs: &mut OutputPin, manual_cs: bool) {
	for _ in 0..3 {
		let rx = read_dev_id(spi, cs, manual_cs);
		let id = u32::from_le_bytes([rx[1], rx[2], rx[3], rx[4]]);
		let tag = match id {
			0xDECA0302 | 0xDECA0312 => "  <-- OK, Chip antwortet!",
			0x0000_0000 => "  (nur Nullen)",
			0xFFFF_FFFF => "  (nur Einsen)",
			_ => "  (anderer Wert)",
		};
		println!("{:<16} DEV_ID = 0x{:08X}  {:02X?}{}", name, id, rx, tag);
		thread::sleep(Duration::from_millis(50));
	}
}

fn main() {
	let gpio = Gpio::new().expect("Failed to configure GPIO");
	println!("GPIO8 vor Start: Modus {:?}\n", gpio.get(8).unwrap().mode());

	let mut spi = Spi::new(Bus::Spi0, SlaveSelect::Ss0, 1_000_000, Mode::Mode0)
		.expect("Failed to configure the spi");
	let mut cs = gpio.get(8).expect("CS").into_output();
	cs.set_high();

	// Reset: RSTn kurz Low, dann loslassen
	let mut reset = gpio.get(25).expect("RSTn").into_io(GpioMode::Output);
	reset.set_pullupdown(PullUpDown::PullUp);
	reset.set_low();
	thread::sleep(Duration::from_millis(2));
	reset.set_mode(GpioMode::Input);
	thread::sleep(Duration::from_millis(10));

	// MISO-Pegel bei CS High / CS Low mit Pull-up (GPLEV ist auch im Alt0-Modus lesbar)
	let mut miso = gpio.get(9).expect("MISO").into_io(GpioMode::Alt0);
	miso.set_pullupdown(PullUpDown::PullUp);
	thread::sleep(Duration::from_millis(1));
	let lvl_cs_high = miso.read();
	cs.set_low();
	thread::sleep(Duration::from_millis(1));
	let lvl_cs_low = miso.read();
	cs.set_high();
	println!("MISO mit Pull-up:  CS High -> {:?},  CS Low -> {:?}", lvl_cs_high, lvl_cs_low);
	if lvl_cs_high == Level::Low {
		println!("  !! MISO ist Low obwohl der Chip nicht ausgewaehlt ist -> etwas zieht MISO auf GND");
	}
	println!();

	show("B MISO Pull-up", &mut spi, &mut cs, true);
	miso.set_pullupdown(PullUpDown::Off);
	thread::sleep(Duration::from_millis(1));

	show("A Basis 1 MHz", &mut spi, &mut cs, true);

	spi.set_clock_speed(100_000).expect("clock");
	show("C 100 kHz", &mut spi, &mut cs, true);
	spi.set_clock_speed(1_000_000).expect("clock");

	show("D Kernel-CS", &mut spi, &mut cs, false);

	spi.set_mode(Mode::Mode3).expect("mode");
	cs.set_high();
	show("E Mode3", &mut spi, &mut cs, true);
	spi.set_mode(Mode::Mode0).expect("mode");

	// CS fuer Messung mit Multimeter 5 s auf Low halten
	println!("\nCSn wird jetzt 5 s auf Low gehalten: am EVB-Pin CSn sollten ~0 V anliegen.");
	cs.set_low();
	thread::sleep(Duration::from_secs(5));
	cs.set_high();
	println!("CSn wieder High (~3,3 V). Fertig.");
}

/*
	Pin-Test: prueft die Kabel zwischen Pi und DWM3000EVB.

	Schaltet nacheinander CLK, MOSI und CSn fuer einige Sekunden auf 3,3 V,
	alle anderen auf 0 V. Mit dem Multimeter (DC-Spannung, schwarz an GND)
	am jeweiligen Pin des EVB messen: nur der angesagte Pin darf ~3,3 V zeigen.

	MISO kann so nicht getestet werden (Ausgang des DW3000), dafuer
	Durchgang messen: Pi stromlos, Pi-Pin 21 <-> MISO-Pin am EVB.

	Start: cargo build --release --bin util_pin_test
	       sudo ../target/release/util_pin_test
	Die SPI-Pins werden beim Beenden automatisch wieder auf SPI (Alt0) gesetzt.
*/
use rppal::gpio::Gpio;

use std::thread;
use std::time::Duration;

const HOLD_SECS: u64 = 6;

fn main() {
	let gpio = Gpio::new().expect("Failed to configure GPIO");

	// (GPIO, Signal am EVB, physischer Pin am Pi)
	let pins_def = [(11u8, "CLK ", 23u8), (10, "MOSI", 19), (8, "CSn ", 24)];

	let mut pins: Vec<_> = pins_def
		.iter()
		.map(|(nr, _, _)| {
			let mut p = gpio.get(*nr).expect("Failed to get pin").into_output();
			p.set_low();
			p
		})
		.collect();

	println!("Multimeter: schwarz an GND, rot nacheinander an CLK, MOSI, CSn am EVB.");
	println!("Nur der angesagte Pin darf ~3,3 V zeigen, die anderen ~0 V.\n");

	for runde in 1..=2 {
		println!("--- Runde {} ---", runde);
		for i in 0..pins.len() {
			for p in pins.iter_mut() {
				p.set_low();
			}
			pins[i].set_high();
			let (nr, name, phys) = pins_def[i];
			println!(
				"{} = 3,3 V  (GPIO{}, Pi-Pin {})  -> jetzt am EVB-Pin {} messen ({} s)",
				name, nr, phys, name.trim(), HOLD_SECS
			);
			thread::sleep(Duration::from_secs(HOLD_SECS));
		}
	}

	for p in pins.iter_mut() {
		p.set_low();
	}
	println!("\nFertig. Wenn alle drei richtig waren: Durchgang von MISO (Pi-Pin 21) zum EVB messen.");
}

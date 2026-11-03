/*
	Verkabelungs-Scan: liest DEV_ID per Bit-Banging (Software-SPI, ~5 kHz)
	mit allen 24 moeglichen Zuordnungen von CLK/MOSI/MISO/CSn auf die
	Pi-Pins GPIO8/9/10/11 (Pin 24/21/19/23). Findet z. B. vertauschte Kabel.

	Die Zuordnung, bei der 0xDECA0302 gelesen wird, ist die echte Verkabelung.

	Start: cargo build --release --bin util_wire_scan
	       sudo ../target/release/util_wire_scan
	Die Pins werden beim Beenden wieder auf SPI (Alt0) zurueckgesetzt.
*/
use rppal::gpio::{Gpio, IoPin, Level, Mode as GpioMode, PullUpDown};

use std::thread;
use std::time::Duration;

const GPIOS: [u8; 4] = [8, 9, 10, 11];

fn phys(gpio: u8) -> u8 {
	match gpio {
		8 => 24,
		9 => 21,
		10 => 19,
		11 => 23,
		_ => 0,
	}
}

fn half_bit() {
	thread::sleep(Duration::from_micros(50));
}

/// Liest DEV_ID per Software-SPI (Mode0, MSB first). Indizes zeigen in `pins`.
fn bitbang_dev_id(pins: &mut [IoPin], clk: usize, mosi: usize, miso: usize, cs: usize) -> [u8; 5] {
	for (i, p) in pins.iter_mut().enumerate() {
		if i == miso {
			p.set_mode(GpioMode::Input);
			p.set_pullupdown(PullUpDown::PullUp);
		} else {
			p.set_pullupdown(PullUpDown::Off);
			p.set_mode(GpioMode::Output);
		}
	}
	pins[cs].set_high();
	pins[clk].set_low();
	pins[mosi].set_low();
	thread::sleep(Duration::from_millis(1));

	let tx = [0x00u8, 0x00, 0x00, 0x00, 0x00];
	let mut rx = [0u8; 5];

	pins[cs].set_low();
	half_bit();
	for (b, byte) in tx.iter().enumerate() {
		for bit in (0..8).rev() {
			if (byte >> bit) & 1 == 1 { pins[mosi].set_high() } else { pins[mosi].set_low() }
			half_bit();
			pins[clk].set_high();
			if pins[miso].read() == Level::High {
				rx[b] |= 1 << bit;
			}
			half_bit();
			pins[clk].set_low();
		}
	}
	half_bit();
	pins[cs].set_high();

	// alles wieder hochohmig, damit keine Ausgaenge gegeneinander treiben
	for p in pins.iter_mut() {
		p.set_mode(GpioMode::Input);
	}
	rx
}

fn main() {
	let gpio = Gpio::new().expect("Failed to configure GPIO");

	// Reset: RSTn kurz Low, dann loslassen
	let mut reset = gpio.get(25).expect("RSTn").into_io(GpioMode::Output);
	reset.set_low();
	thread::sleep(Duration::from_millis(2));
	reset.set_mode(GpioMode::Input);
	thread::sleep(Duration::from_millis(10));

	let mut pins: Vec<IoPin> = GPIOS
		.iter()
		.map(|nr| gpio.get(*nr).expect("pin").into_io(GpioMode::Input))
		.collect();

	println!("Erwartet: CLK=GPIO11(Pin23) MOSI=GPIO10(Pin19) MISO=GPIO9(Pin21) CSn=GPIO8(Pin24)\n");

	let mut found = false;
	for clk in 0..4 {
		for mosi in 0..4 {
			for miso in 0..4 {
				for cs in 0..4 {
					let mut s = [clk, mosi, miso, cs];
					s.sort();
					if s != [0, 1, 2, 3] {
						continue;
					}
					let rx = bitbang_dev_id(&mut pins, clk, mosi, miso, cs);
					let id = u32::from_le_bytes([rx[1], rx[2], rx[3], rx[4]]);
					let ok = id == 0xDECA0302 || id == 0xDECA0312;
					if ok {
						found = true;
					}
					println!(
						"CLK=Pin{:<2} MOSI=Pin{:<2} MISO=Pin{:<2} CSn=Pin{:<2}  DEV_ID=0x{:08X}{}",
						phys(GPIOS[clk]), phys(GPIOS[mosi]), phys(GPIOS[miso]), phys(GPIOS[cs]),
						id,
						if ok { "   <-- TREFFER" } else { "" }
					);
				}
			}
		}
	}

	println!();
	if found {
		println!("Treffer gefunden: so ist das EVB tatsaechlich an den Pi angeschlossen.");
	} else {
		println!("Kein Treffer: der Chip antwortet bei keiner Zuordnung (Strom/GND/Reset pruefen).");
	}
}

/*
	A simple exemple to be used with simple_send. It will receive a frame on a loop
*/
use rppal::gpio::{Gpio, Mode as GpioMode, OutputPin, PullUpDown};
use rppal::spi::{Bus, Mode, SlaveSelect, Spi};

use std::thread;
use std::time::Duration;

use dw3000::{
	self,
	hl,
	ll,
	Config
};
use nb::block;

/// Clears all RX event and error flags (write-1-to-clear). r_wait reports
/// any error flag that is still set, so without this one error would be
/// reported again on every following reception.
fn clear_rx_status(ll: &mut ll::DW3000<Spi, OutputPin>) {
	ll.sys_status()
		.write(|w| {
			w.rxprd(0b1)
				.rxsfdd(0b1)
				.ciadone(0b1)
				.rxphd(0b1)
				.rxphe(0b1)
				.rxfr(0b1)
				.rxfcg(0b1)
				.rxfce(0b1)
				.rxfsl(0b1)
				.rxfto(0b1)
				.ciaerr(0b1)
				.rxovrr(0b1)
				.rxpto(0b1)
				.rxsto(0b1)
				.arfe(0b1)
		})
		.expect("Failed to clear RX status");
}

fn main() -> ! {
    
    /******************************************************* */
	/************        BASIC CONFIGURATION      ********** */
	/******************************************************* */

    let spi = Spi::new(Bus::Spi0, SlaveSelect::Ss0, 1_000_000, Mode::Mode0)
        .expect("Failed to configure the spi");
    let gpio = Gpio::new()
        .expect("Failed to configure GPIO");
    let cs = gpio
        .get(8)
        .expect("Failed to set up CS PIN")
        .into_output();

    /****************************************************** */
	/*****                DW3000 RESET              ******* */
	/****************************************************** */

    // RSTn = GPIO25. Kurz auf Low ziehen und dann loslassen (Eingang).
    // RSTn ist Open-Drain und darf laut Datenblatt nicht aktiv High getrieben werden.
    let mut reset = gpio
        .get(25)
        .expect("Failed to set up RESET PIN")
        .into_io(GpioMode::Output);
    // Pi-interner Pull-down (GPIO9-27 nach dem Booten) wuerde RSTn halb auf Low ziehen.
    // Stattdessen Pi-Pull-up (~50k) einschalten: RSTn sicher High, aber nicht aktiv getrieben.
    reset.set_pullupdown(PullUpDown::PullUp);
    reset.set_low();
    thread::sleep(Duration::from_millis(2));
    reset.set_mode(GpioMode::Input);
    thread::sleep(Duration::from_millis(10));

    /****************************************************** */
	/*********         DW3000 CONFIGURATION        ******** */
	/****************************************************** */

	let mut dw3000 = hl::DW3000::new(spi, cs)
		.init()
		.expect("Failed init.")
		.config(Config::default())
		.expect("Failed config.");
	dw3000.enable_leds(true).expect("Failed to enable LEDs");

    thread::sleep(Duration::from_millis(500));
    println!("Init OK");

	loop {
		// Initiate Reception
		let mut buffer = [0; 1024];
		clear_rx_status(dw3000.ll());
        let mut receiving = dw3000
			.receive(Config::default())
			.expect("Failed configure receiver.");

		// Waiting for an incomming frame
	    let result = match block!(receiving.r_wait(&mut buffer)) {
			Ok(t) => t,
			Err(e) => {
				// Frame(..) = frame received fine (CRC good), but it is not
				// an IEEE 802.15.4 frame the ieee802154 crate can parse.
				println!("Error: {:?}", e);
				dw3000 = receiving.finish_receiving().expect("Failed to finish receiving");
				continue // Start a new loop iteration
			}
		};

		println!("Frame received at {}", result.rx_time.value());
		dw3000 = receiving.finish_receiving().expect("Failed to finish receiving");
	}
}

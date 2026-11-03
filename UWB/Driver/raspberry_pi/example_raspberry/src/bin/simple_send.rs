/*
	A simple exemple to be used with simple_receive. It will send a frame on a loop
*/
use rppal::gpio::{Gpio, Mode as GpioMode, PullUpDown};
use rppal::spi::{Bus, Mode, SlaveSelect, Spi};

use std::thread;
use std::time::Duration;

use dw3000::{
	self,
	hl,
	Config
};
use nb::block;

fn main() -> ! {
    
    /******************************************************* */
	/************        BASIC CONFIGURATION      ********** */
	/******************************************************* */

    let spi = Spi::new(Bus::Spi0, SlaveSelect::Ss0, 4_500_000, Mode::Mode0)
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

    thread::sleep(Duration::from_millis(500));
    println!("Init OK");

	loop {
        // Initiate Sending
		let mut sending = dw3000
            .send(&[1, 2, 3, 4, 5], hl::SendTime::Now, Config::default())
            .expect("Failed configure transmitter");

        // Waiting for the frame to be sent
        let result = match block!(sending.s_wait()) {
            Ok(t) => t,
            Err(_e) => {
                println!("Error");
                dw3000 = sending.finish_sending().expect("Failed to finish sending");
                continue // Start a new loop iteration
            }
        };

		println!("Sending at {}", result.value());
		dw3000 = sending.finish_sending().expect("Failed to finish sending");
	}
}

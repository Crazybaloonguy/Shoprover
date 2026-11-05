use rppal::gpio::{Gpio, Mode as GpioMode, OutputPin, PullUpDown};
use rppal::spi::{Bus, Mode, SlaveSelect, Spi};

use std::thread;
use std::time::Duration;

use dw3000::{
	self,
	hl,
	Config,
	FastCommand,
	time::Instant
};
use nb::block;

type Dw = hl::DW3000<Spi, OutputPin, hl::Ready>;

/// Waits for a good frame and returns its RX timestamp and MAC payload.
/// RX errors are printed and the receiver is re-enabled, instead of aborting
/// the program.
fn receive_frame(dw3000: Dw) -> (Dw, u64, Vec<u8>) {
	let mut receiving = dw3000
		.receive(Config::default())
		.expect("Failed configure receiver.");
	loop {
		let mut buffer = [0; 1024];
		match block!(receiving.r_wait(&mut buffer)) {
			Ok(msg) => {
				let rx_time = msg.rx_time.value();
				let payload = msg.frame.payload.to_vec();
				let dw3000 = receiving
					.finish_receiving()
					.expect("Failed to finish receiving");
				return (dw3000, rx_time, payload);
			},
			Err(e) => {
				let ffen = receiving.ll().sys_cfg().read().map(|r| r.ffen()).unwrap_or(0xFF);
				println!("RX error {:?} (frame filtering enabled: {}), listening again", e, ffen);

				// Error flags are write-1-to-clear; r_wait would report them again otherwise.
				receiving.ll()
					.sys_status()
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
				receiving.fast_cmd(FastCommand::CMD_RX).expect("Failed to restart receiver");
			},
		}
	}
}

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
		/****************************************************** */
		/*********    WAITING REQUEST FROM INITIATOR   ******** */
		/****************************************************** */
		println!("FIRST STEP : Waiting measurement request ...");

		let (dw, t2, _) = receive_frame(dw3000);
		dw3000 = dw;


		/****************************************************** */
		/*********       RESPONDING TO INITIATOR       ******** */
		/****************************************************** */
		println!("SECOND STEP : Offset response");

		// The buffer is empty because the initiator does not need timestamps
		// The final computation is done by the responder
		let delay_to_reply = t2 + (5000 * 63898); // micros * clock speed
		let mut sending = dw3000
			.send(
				&[0],
				hl::SendTime::Delayed(Instant::new(delay_to_reply).unwrap()),
				Config::default())
			.expect("Failed configure transmitter");
	    let result = block!(sending.s_wait());
	    let t3: u64 = result.unwrap().value();
	    dw3000 = sending.finish_sending().expect("Failed to finish sending");


		/****************************************************** */
		/*********          WAITING T1, T4, T5         ******** */
		/****************************************************** */
    	println!("THIRD STEP : Waiting for an answer...");

		let (dw, t6, x) = receive_frame(dw3000);
		dw3000 = dw;
		if x.len() < 15 {
			println!("Final too short ({} bytes), restarting\n", x.len());
			continue;
		}
		let t1: u64 = ((x[0] as u64) << (8 * 4)) 
					+ ((x[1] as u64) << (8 * 3))
					+ ((x[2] as u64) << (8 * 2))
					+ ((x[3] as u64) <<  8)
					+  (x[4] as u64);
		let t4: u64 = ((x[5] as u64) << (8 * 4)) 
					+ ((x[6] as u64) << (8 * 3))
					+ ((x[7] as u64) << (8 * 2))
					+ ((x[8] as u64) <<  8)
					+  (x[9] as u64);
		let t5 : u64= ((x[10] as u64) << (8 * 4)) 
					+ ((x[11] as u64) << (8 * 3))
					+ ((x[12] as u64) << (8 * 2))
					+ ((x[13] as u64) <<  8)
					+ ( x[14] as u64);

		println!("Distance = {} m", calc_distance_double(t1, t2, t3, t4, t5, t6));
		println!("--- RTT FINISHED ---\n");
	}
}

fn calc_distance_double(t1: u64, t2: u64, t3: u64, t4: u64, t5: u64, t6: u64) -> f64 {
	let f: f64 = 1.0/499200000.0/128.0; // Clock speed
	let s_light: f64 = 299792458.0; // speed of light m/s

	let tround1: f64 = (t4 - t1) as f64;
	let treply1: f64 = (t3 - t2) as f64;
	let tround2: f64 = (t6 - t3) as f64;
	let treply2: f64 = (t5 - t4) as f64;

	let tof_tick: f64 = (((tround1 as u128 * tround2 as u128) - (treply1 as u128 * treply2 as u128 )) / ((tround1 + treply1 + tround2 + treply2) as u128)) as f64;
	let tof_sec: f64 = tof_tick * f;

	let distance: f64 = tof_sec * s_light;	
	distance
}
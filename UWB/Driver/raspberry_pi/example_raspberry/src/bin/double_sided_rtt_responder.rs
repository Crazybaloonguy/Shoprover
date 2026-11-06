use rppal::gpio::{Gpio, Mode as GpioMode, OutputPin, PullUpDown};
use rppal::spi::{Bus, Mode, SlaveSelect, Spi};

use std::thread;
use std::time::Duration;

use dw3000::{
	self,
	hl,
	ll,
	Config,
	FastCommand,
	time::{Instant, TIME_MAX},
};
use nb::block;

type Dw = hl::DW3000<Spi, OutputPin, hl::Ready>;

/// Poll RX -> response TX on this side: 5000 us in DW3000 time units
/// (1 us = 63897.6 ticks). The Pico tag centres its RX window on this value.
const REPLY_DELAY_TICKS: u64 = 5000 * 63898;

/// Clears all RX event and error flags (write-1-to-clear).
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
				.rxprej(0b1)
		})
		.expect("Failed to clear RX status");
}

/// Waits for a good frame and returns its RX timestamp and MAC payload
/// (the payload still ends with the 2 FCS bytes).
/// RX errors are printed and the receiver is re-enabled, instead of aborting
/// the program.
fn receive_frame(mut dw3000: Dw) -> (Dw, u64, Vec<u8>) {
	// r_wait reports any error flag that is set, also ones left over from
	// before this reception (e.g. from init). Start with a clean status.
	clear_rx_status(dw3000.ll());

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
				// Raw registers, so the cause can be read from the datasheet:
				// SYS_STATUS bit 29 = ARFE, bit 14 = RXFCG, bit 15 = RXFCE, ...
				// SYS_CFG bit 0 = FFEN (frame filtering on).
				let status = receiving.ll().sys_status().read()
					.map(|r| format!("{:?}", r))
					.unwrap_or_else(|_| "read failed".into());
				let sys_cfg = receiving.ll().sys_cfg().read()
					.map(|r| format!("{:?}", r))
					.unwrap_or_else(|_| "read failed".into());
				println!("RX error {:?} (SYS_STATUS {}, SYS_CFG {}), listening again", e, status, sys_cfg);

				// Receiver off, flags cleared (r_wait would report them
				// again otherwise), receiver on.
				receiving.force_idle().expect("Failed to force idle");
				clear_rx_status(receiving.ll());
				receiving.fast_cmd(FastCommand::CMD_RX).expect("Failed to restart receiver");
			},
		}
	}
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

    thread::sleep(Duration::from_millis(500));
    println!("Init OK");


	// A frame that arrives while the final is expected but is too short to be
	// one is the tag's next poll (it missed our response). Its RX time is kept
	// here so it is answered instead of being lost.
	let mut pending_poll: Option<u64> = None;

    loop {
		/****************************************************** */
		/*********    WAITING REQUEST FROM INITIATOR   ******** */
		/****************************************************** */
		let t2 = match pending_poll.take() {
			Some(t2) => t2,
			None => {
				println!("FIRST STEP : Waiting measurement request ...");
				let (dw, t2, _) = receive_frame(dw3000);
				dw3000 = dw;
				t2
			},
		};


		/****************************************************** */
		/*********       RESPONDING TO INITIATOR       ******** */
		/****************************************************** */
		println!("SECOND STEP : Offset response");

		// The payload is a dummy byte: the initiator does not need our
		// timestamps, the final computation is done here.
		// The device clock wraps every 2^40 ticks (~17.2 s), so the reply time
		// is taken modulo 2^40 (TIME_MAX = 2^40 - 1).
		let delay_to_reply = (t2 + REPLY_DELAY_TICKS) & TIME_MAX;
		let mut sending = dw3000
			.send(
				&[0],
				hl::SendTime::Delayed(Instant::new(delay_to_reply).unwrap()),
				Config::default())
			.expect("Failed configure transmitter");
		let t3: u64 = match block!(sending.s_wait()) {
			Ok(t3) => t3.value(),
			Err(e) => {
				// DelayedSendTooLate: this host needed more than the reply
				// delay. The chip would send ~17 s later; finish_sending aborts.
				println!("Response not sent ({:?}), restarting\n", e);
				dw3000 = sending.finish_sending().expect("Failed to finish sending");
				continue;
			},
		};
		dw3000 = sending.finish_sending().expect("Failed to finish sending");


		/****************************************************** */
		/*********          WAITING T1, T4, T5         ******** */
		/****************************************************** */
		println!("THIRD STEP : Waiting for an answer...");

		let (dw, t6, x) = receive_frame(dw3000);
		dw3000 = dw;
		if x.len() < 15 {
			println!("Final too short ({} bytes), treating it as a new poll\n", x.len());
			pending_poll = Some(t6);
			continue;
		}
		let t1 = read_ts_be(&x[0..5]);
		let t4 = read_ts_be(&x[5..10]);
		let t5 = read_ts_be(&x[10..15]);

		println!("Distance = {:.3} m", calc_distance_double(t1, t2, t3, t4, t5, t6));
		println!("--- RTT FINISHED ---\n");
	}
}

/// 40-bit timestamp, most significant byte first (as sent by the Pico tag).
fn read_ts_be(bytes: &[u8]) -> u64 {
	bytes.iter().fold(0u64, |acc, &b| (acc << 8) | b as u64)
}

/// `later - earlier` in device ticks, correct across the 40-bit wraparound.
fn ticks_between(earlier: u64, later: u64) -> i128 {
	(later.wrapping_sub(earlier) & TIME_MAX) as i128
}

fn calc_distance_double(t1: u64, t2: u64, t3: u64, t4: u64, t5: u64, t6: u64) -> f64 {
	let tick_s: f64 = 1.0 / 499_200_000.0 / 128.0; // one device time unit (~15.65 ps)
	let s_light: f64 = 299_792_458.0; // speed of light m/s

	let tround1 = ticks_between(t1, t4); // tag:    poll TX  -> resp RX
	let treply1 = ticks_between(t2, t3); // anchor: poll RX  -> resp TX
	let tround2 = ticks_between(t3, t6); // anchor: resp TX  -> final RX
	let treply2 = ticks_between(t4, t5); // tag:    resp RX  -> final TX

	// Asymmetric DS-TWR formula. i128 so the products cannot overflow and a
	// slightly negative result (uncalibrated antenna delays) stays visible.
	let num = tround1 * tround2 - treply1 * treply2;
	let den = tround1 + treply1 + tround2 + treply2;
	let tof_ticks = num as f64 / den as f64;

	tof_ticks * tick_s * s_light
}

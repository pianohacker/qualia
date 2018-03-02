#[macro_use]
extern crate clap;
#[macro_use]
extern crate failure;
#[macro_use]
extern crate lazy_static;

use clap::App;
use failure::Error;
use std::path::Path;

mod commands;
mod common;

fn main() {
	if let Err(e) = main_impl() {
		eprintln!("{}", e);
	}
}

fn main_impl() -> Result<(), Error> {
	let mut clap_app = App::new("qualia")
		.version(crate_version!())
		.author("Jesse Weaver <pianohacker@gmail.com>")
		.about("Metadata-focused file organizer");

	clap_app = commands::register(clap_app);

	let app_settings = common::default_settings();

	let matches = clap_app.get_matches();

	commands::run(app_settings, matches)
}

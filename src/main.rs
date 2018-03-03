#[macro_use]
extern crate clap;
#[macro_use]
extern crate failure;
#[macro_use]
extern crate lazy_static;
extern crate rusqlite;

use clap::{App, Arg, ArgMatches};
use failure::Error;
use std::path::Path;

mod commands;
mod common;
mod collection;

fn main() {
	if let Err(e) = main_impl() {
		eprintln!("{}", e);
	}
}

fn apply_matches_to_settings(app_settings: &mut common::AppSettings, matches: &ArgMatches) {
	if let Some(collection_dir) = matches.value_of("collection-dir") {
		app_settings.collection_dir = From::from(Path::new(collection_dir));
	}
}

fn main_impl() -> Result<(), Error> {
	let mut clap_app = App::new("qualia")
		.version(crate_version!())
		.author("Jesse Weaver <pianohacker@gmail.com>")
		.about("Metadata-focused file organizer")
		.arg(
			Arg::with_name("collection-dir")
				.short("d")
				.takes_value(true),
		);

	clap_app = commands::register(clap_app);

	let mut app_settings = common::default_settings();
	let matches = clap_app.get_matches();

	apply_matches_to_settings(&mut app_settings, &matches);

	commands::run(app_settings, matches)
}

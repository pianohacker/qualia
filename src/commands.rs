use clap::{App, Arg, ArgMatches, SubCommand};
use std::collections::HashMap;
use std::fs::metadata;
use std::sync::Mutex;

use common;
use failure::Error;

lazy_static! {
	static ref COMMAND_MAP: Mutex<HashMap<&'static str, fn (common::AppSettings, &ArgMatches) -> Result<(), Error>>> = Mutex::new(HashMap::new());
}

macro_rules! subcommand {
    ($app:tt, $name:expr, $subcommand:expr, $impl:expr) => {
        $app = $app.subcommand($subcommand);
        COMMAND_MAP.lock().unwrap().insert($name, $impl);
    }
}

pub fn register<'a, 'b>(mut app: App<'a, 'b>) -> App<'a, 'b> {
	subcommand!(
		app,
		"add",
		SubCommand::with_name("add").arg(
			Arg::with_name("filename")
				.index(1)
				.required(true)
				.multiple(true)
				.takes_value(true)
		),
		|settings, matches| {
			for filename in matches.values_of("filename").unwrap() {
				metadata(filename).map_err(|e| format_err!("{}: {}", filename, e))?;
			}

			println!("add!");

			Ok(())
		}
	);

	app
}

pub fn run<'a>(app_settings: common::AppSettings, matches: ArgMatches<'a>) -> Result<(), Error> {
	let command_map = COMMAND_MAP.lock().unwrap();

	let subcmd = matches.subcommand_name().expect("no subcommand given");
	let command_impl = command_map
		.get(subcmd)
		.expect("should not be reached, subcommand given but unknown");

	command_impl(app_settings, matches.subcommand_matches(subcmd).unwrap())
}

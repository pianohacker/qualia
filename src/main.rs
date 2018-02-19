#[macro_use]
extern crate clap;
extern crate failure;

use clap::App;
use failure::Error;

fn main() {
	main_impl().expect("success");
}

fn main_impl() -> Result<(), Error> {
	let matches = App::new("qualia")
		.version(crate_version!())
		.author("Jesse Weaver <pianohacker@gmail.com>")
		.about("Metadata-focused file organizer")
		.get_matches();
	println!("yo");

	Ok(())
}

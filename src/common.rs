use std::env;
use std::path::PathBuf;

pub struct AppSettings {
	pub collection_dir: PathBuf,
}

pub fn default_settings() -> AppSettings {
	let mut collection_dir = env::home_dir().expect("home directory not defined");

	collection_dir.push("q");

	return AppSettings {
		collection_dir: collection_dir,
	};
}

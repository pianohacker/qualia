use std::env;
use std::path::PathBuf;

pub struct AppSettings {
	pub db_path: PathBuf,
}

pub fn default_settings() -> AppSettings {
	let mut db_path = env::home_dir().expect("home directory not defined");

	db_path.push("q");

	return AppSettings { db_path };
}

use failure::Error;
use std::fs;
use std::path::{Path, PathBuf};
use rusqlite::Connection;

pub struct Collection {
	collection_dir: PathBuf,
	internal_dir: PathBuf,
	connection: Connection,
}

impl Collection {
	fn setup_if_needed(internal_dir: &PathBuf) -> Result<(), Error> {
		if !internal_dir.is_dir() {
			fs::create_dir_all(internal_dir)?;
		}

		Ok(())
	}

	pub fn open(collection_dir: PathBuf) -> Result<Collection, Error> {
		let mut internal_dir = collection_dir.clone();
		internal_dir.push(".qualia");

		Self::setup_if_needed(&internal_dir)?;

		let mut sqlite_path = internal_dir.clone();
		sqlite_path.push("qualia.db");

		let connection = Connection::open(sqlite_path)?;

		Ok(Collection {
			connection,
			collection_dir,
			internal_dir,
		})
	}

	pub fn add<P: AsRef<Path>>(&self, filename: P) -> () {
		println!(
			"Adding: {:?} to {:?}",
			filename.as_ref(),
			self.collection_dir
		);
	}
}

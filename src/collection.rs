use failure::Error;
use digest::generic_array;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use rusqlite::Connection;

pub struct Collection {
	collection_dir: PathBuf,
	internal_dir: PathBuf,
	connection: Connection,
}

type Sha256Hash = generic_array::GenericArray<u8, generic_array::typenum::U32>;

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

	fn prepare_hash_internal_path(&self, hash: &Sha256Hash) -> Result<PathBuf, Error> {
		let mut dest_path = self.internal_dir.clone();
		dest_path.push("files");
		// `:.1x` gives us one byte or two hex nybbles
		dest_path.push(format!("{:.1x}", hash));
		fs::create_dir_all(&dest_path)?;

		dest_path.push(format!("{:x}", hash));

		Ok(dest_path)
	}

	fn copy_to_internal(&self, source_path: &Path, hash: &Sha256Hash) -> Result<(), Error> {
		let dest_path = self.prepare_hash_internal_path(hash)?;

		fs::copy(source_path, dest_path)?;

		Ok(())
	}

	fn copy_to_visible(&self, source_path: &Path, hash: &Sha256Hash) -> Result<(), Error> {
		let dest_path = self.prepare_hash_internal_path(hash)?;

		let mut link_path = self.collection_dir.clone();
		link_path.push(source_path.file_name().unwrap());

		fs::hard_link(dest_path, link_path)?;

		Ok(())
	}

	pub fn add<P: AsRef<Path>>(&self, source_path: P) -> Result<(), Error> {
		let mut file = fs::File::open(source_path.as_ref())?;
		let hash = Sha256::digest_reader(&mut file)?;

		self.copy_to_internal(source_path.as_ref(), &hash)?;
		self.copy_to_visible(source_path.as_ref(), &hash)?;

		println!(
			"Adding: {:?} to {:?}: {:x}",
			source_path.as_ref(),
			self.collection_dir,
			hash
		);

		Ok(())
	}
}

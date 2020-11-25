use rusqlite::{params, Connection};
use std::collections::HashMap;
use std::path::Path;
use std::result::Result as Result_;
use thiserror::Error;

pub type Result<T, E = StoreError> = Result_<T, E>;

#[derive(Error, Debug)]
pub enum StoreError {
    #[error("database error")]
    Sqlite(#[from] rusqlite::Error),

    #[error("could not de/serialize object")]
    Serialization(#[from] serde_json::Error),
}

trait AsStoreResult<T> {
    fn as_store_result(self) -> Result<T>;
}

impl<T, E> AsStoreResult<T> for Result_<T, E>
where
    E: Into<StoreError>,
{
    fn as_store_result(self) -> Result<T> {
        self.map_err(|e| e.into())
    }
}

pub type Object = HashMap<String, serde_json::Value>;

pub struct Store {
    conn: Connection,
}

impl Store {
    pub fn open(path: impl AsRef<Path>) -> Result<Store> {
        let mut store = Store {
            conn: Connection::open(path)?,
        };

        // Make SQLite use a write-ahead instead of a delete-based journal; see
        // [the SQLite documentation](https://www.sqlite.org/wal.html) for more info.
        store.conn.pragma_update(None, "journal_mode", &"WAL")?;

        // Check that the JSON1 extension is working.
        store
            .conn
            .prepare("SELECT json(\"{}\")")?
            .query(params![])
            // Explicitly ignore the value.
            .map(|_| {})?;

        store.upgrade_if_needed()?;

        Ok(store)
    }

    fn upgrade_if_needed(&mut self) -> Result<()> {
        // We check the version of the database and upgrade it if necessary.
        // Conveniently, this starts at 0 in an empty database.
        let version = self
            .conn
            .prepare("SELECT user_version from pragma_user_version")?
            .query_row(params![], |row| row.get::<usize, i64>(0))? as usize;

        // We use `AUTOINCREMENT` on the objects table so that IDs are not reused.
        let updates = [
            "
                CREATE TABLE objects (
                    object_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    properties TEXT
                );
            ",
            "
                CREATE TABLE object_changes (
                    serial INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    object_id INTEGER,
                    action TEXT,
                    previous TEXT
                );
                CREATE TABLE checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    serial INTEGER
                );
            ",
        ];

        // We set the `user_version` after each update to ensure updates are not applied twice if one
        // in a sequence of updates fails.
        for (version, update) in updates.iter().enumerate().skip(version) {
            self.conn.execute_batch(update)?;
            self.conn
                .pragma_update(None, "user_version", &(version as i64))?;
        }

        Ok(())
    }

    pub fn all(&self) -> Collection {
        Collection { conn: &self.conn }
    }

    pub fn add(&mut self, object: Object) -> Result<()> {
        let object_serialized = serde_json::to_string(&object)?;

        self.conn
            .prepare("INSERT INTO objects(properties) VALUES(?)")?
            .execute(params![object_serialized])?;

        Ok(())
    }
}

pub struct Collection<'a> {
    conn: &'a Connection,
}

impl<'a> Collection<'a> {
    pub fn len(&self) -> Result<usize> {
        Ok(self
            .conn
            .prepare("SELECT COUNT(*) FROM objects")?
            // This workaround can be removed when https://github.com/rusqlite/rusqlite/issues/700
            // is closed
            .query_row(params![], |row| row.get::<usize, i64>(0))? as usize)
    }

    pub fn iter(&self) -> Result<impl Iterator<Item = Object> + 'a> {
        Ok(self
            .conn
            .prepare("SELECT properties FROM objects")?
            .query_and_then(params![], |row| row.get::<usize, String>(0))?
            .map(|r| {
                r.as_store_result().and_then(|serialized_object| {
                    serde_json::from_str(&serialized_object).as_store_result()
                })
            })
            .collect::<Result<Vec<Object>>>()?
            .into_iter())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempdir::TempDir;

    fn open_store(tempdir: &TempDir, name: &str) -> Store {
        Store::open(tempdir.path().join(name)).unwrap()
    }

    fn test_dir() -> TempDir {
        TempDir::new("qualia-store").unwrap()
    }

    fn mkobject<'a>(proplist: &'a [(&'a str, &'a str)]) -> Object {
        proplist
            .iter()
            .cloned()
            .map(|(k, v)| (k.to_string(), serde_json::Value::String(v.to_string())))
            .collect()
    }

    fn sort_objects(objects: &mut Vec<Object>) {
        objects.sort_by_key(|o| {
            o.get("name")
                .and_then(|v| Some(v.as_str().unwrap_or("")))
                .unwrap_or("")
                .to_string()
        })
    }

    #[test]
    fn new_store_is_empty() {
        assert_eq!(
            open_store(&test_dir(), "store.qualia").all().len().unwrap(),
            0
        );
    }

    #[test]
    fn added_objects_can_be_found() {
        let test_dir = test_dir();
        let mut store = open_store(&test_dir, "store.qualia");

        store.add(mkobject(&[("name", "b"), ("c", "d")])).unwrap();
        store.add(mkobject(&[("name", "d"), ("c", "f")])).unwrap();
        store.add(mkobject(&[("name", "c"), ("c", "e")])).unwrap();

        let all = store.all();

        assert_eq!(all.len().unwrap(), 3);
        let mut all_objects = all.iter().unwrap().collect::<Vec<Object>>();
        sort_objects(&mut all_objects);
        assert_eq!(
            all_objects,
            vec![
                mkobject(&[("name", "b"), ("c", "d")]),
                mkobject(&[("name", "c"), ("c", "e")]),
                mkobject(&[("name", "d"), ("c", "f")])
            ],
        );
    }
}

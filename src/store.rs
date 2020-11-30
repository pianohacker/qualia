//! A document store with a flexible query language and built-in undo support.

use regex::Regex;
use rusqlite::{params, Connection};
use std::path::Path;
use std::result::Result as Result_;
use std::sync::Arc;
use thiserror::Error;

use crate::object::*;
use crate::query;

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

        store.add_regexp_function()?;

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
                .pragma_update(None, "user_version", &((version + 1) as i64))?;
        }

        Ok(())
    }

    fn add_regexp_function(&mut self) -> Result<()> {
        // Lifted from https://docs.rs/rusqlite/0.24.1/rusqlite/functions/index.html
        Ok(self.conn.create_scalar_function(
            "regexp",
            2,
            rusqlite::functions::FunctionFlags::SQLITE_UTF8
                | rusqlite::functions::FunctionFlags::SQLITE_DETERMINISTIC,
            move |ctx| {
                assert_eq!(ctx.len(), 2, "called with unexpected number of arguments");
                let regexp: Arc<Regex> = ctx.get_or_create_aux(
                    0,
                    |vr| -> Result<_, Box<dyn std::error::Error + Send + Sync + 'static>> {
                        Ok(Regex::new(vr.as_str()?)?)
                    },
                )?;
                let is_match = {
                    let text = ctx
                        .get_raw(1)
                        .as_str()
                        .map_err(|e| rusqlite::Error::UserFunctionError(e.into()))?;

                    regexp.is_match(text)
                };

                Ok(is_match)
            },
        )?)
    }

    pub fn all(&self) -> Collection {
        Collection {
            conn: &self.conn,
            query: Box::new(query::Empty {}),
        }
    }

    pub fn query(&self, query: Box<dyn query::QueryNode>) -> Collection {
        Collection {
            conn: &self.conn,
            query,
        }
    }

    pub fn add(&mut self, object: Object) -> Result<i64> {
        let object_serialized = serde_json::to_string(&object)?;

        self.conn
            .prepare("INSERT INTO objects(properties) VALUES(?)")?
            .execute(params![object_serialized])?;

        Ok(self.conn.last_insert_rowid() as i64)
    }
}

pub struct Collection<'a> {
    conn: &'a Connection,
    query: Box<dyn query::QueryNode>,
}

impl<'a> Collection<'a> {
    fn prepare_with_query(
        &self,
        prefix: &str,
    ) -> Result<(rusqlite::Statement, Vec<Box<dyn rusqlite::ToSql>>)> {
        let (where_clause, params) = self.query.to_sql_clause();
        Ok((
            self.conn
                .prepare(&format!("{} WHERE {}", prefix, where_clause))?,
            params,
        ))
    }

    pub fn len(&self) -> Result<usize> {
        let (mut statement, params) = self.prepare_with_query("SELECT COUNT(*) FROM objects")?;
        Ok(statement
            // This workaround can be removed when https://github.com/rusqlite/rusqlite/issues/700
            // is closed
            .query_row(params, |row| row.get::<usize, i64>(0))? as usize)
    }

    pub fn iter(&self) -> Result<impl Iterator<Item = Object> + 'a> {
        let (mut statement, params) =
            self.prepare_with_query("SELECT object_id, properties FROM objects")?;

        let rows = statement.query_and_then(params, |row| {
            Ok((row.get::<usize, i64>(0)?, row.get::<usize, String>(1)?))
        })?;

        let result = Ok(rows
            .map(|r: rusqlite::Result<(i64, String)>| {
                r.as_store_result()
                    .and_then(|(object_id, serialized_object)| {
                        let mut object =
                            serde_json::from_str::<Object>(&serialized_object).as_store_result()?;

                        object.insert("object-id".to_string(), PropValue::Number(object_id));
                        Ok(object)
                    })
            })
            .collect::<Result<Vec<Object>>>()?
            .into_iter());

        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempdir::TempDir;

    fn open_store(tempdir: &TempDir, name: &str) -> Store {
        Store::open(tempdir.path().join(name)).unwrap()
    }

    fn test_dir() -> TempDir {
        TempDir::new("qualia-store").unwrap()
    }

    fn mkobject_(proplist: serde_json::Value) -> Object {
        let proplist_map = proplist.as_object().unwrap();

        proplist_map
            .iter()
            .map(|(k, v)| (k.clone(), PropValue::from(v)))
            .collect()
    }

    macro_rules! mkobject {
        ( $($x:tt)* ) => {
            mkobject_(json!({ $($x)* }))
        };
    }

    fn populated_store() -> Result<(Store, TempDir)> {
        let test_dir = test_dir();
        let mut store = open_store(&test_dir, "store.qualia");

        store.add(mkobject!("name": "one", "blah": "blah"))?;
        store.add(mkobject!("name": "two", "blah": "halb"))?;
        store.add(mkobject!("name": "three", "blah": "BLAH"))?;

        Ok((store, test_dir))
    }

    fn sort_objects(objects: &mut Vec<Object>) {
        objects.sort_by_key(|o| {
            o.get("name")
                .expect("test objects should have a name")
                .as_str()
                .expect("`name` of test objects should be a string")
                .clone()
        })
    }

    #[test]
    fn new_store_is_empty() -> Result<()> {
        assert_eq!(open_store(&test_dir(), "store.qualia").all().len()?, 0);

        Ok(())
    }

    #[test]
    fn added_objects_exist() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let all = store.all();

        assert_eq!(all.len()?, 3);
        let mut all_objects = all.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut all_objects);
        assert_eq!(
            all_objects,
            vec![
                mkobject!("name": "one", "blah": "blah", "object-id": 1),
                mkobject!("name": "three", "blah": "BLAH", "object-id": 3),
                mkobject!("name": "two", "blah": "halb", "object-id": 2),
            ],
        );

        Ok(())
    }

    #[test]
    fn added_objects_can_be_found() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let found = store.query(Box::new(query::PropEqual {
            name: "name".to_string(),
            value: PropValue::String("one".to_string()),
        }));

        assert_eq!(found.len()?, 1);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![mkobject!("name": "one", "blah": "blah", "object-id": 1)],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_found_by_their_object_id() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let object_id = store.add(mkobject!("name": "b", "c": "d"))?;

        let found = store.query(Box::new(query::PropEqual {
            name: "object-id".into(),
            value: object_id.into(),
        }));

        assert_eq!(found.len()?, 1);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![mkobject!("name": "b", "c": "d", "object-id": object_id)],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_found_by_like() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let found = store.query(Box::new(query::PropLike {
            name: "blah".into(),
            value: "blah".into(),
        }));

        assert_eq!(found.len()?, 2);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![
                mkobject!("name": "one", "blah": "blah", "object-id": 1),
                mkobject!("name": "three", "blah": "BLAH", "object-id": 3)
            ],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_found_by_and() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let found = store.query(Box::new(query::And(vec![
            Box::new(query::PropEqual {
                name: "name".into(),
                value: "one".into(),
            }),
            Box::new(query::PropLike {
                name: "blah".into(),
                value: "blah".into(),
            }),
        ])));

        assert_eq!(found.len()?, 1);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![mkobject!("name": "one", "blah": "blah", "object-id": 1),],
        );

        Ok(())
    }
}

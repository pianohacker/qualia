//! A document store with a flexible query language and built-in undo support.

use regex::Regex;
use rusqlite::{params, Connection};
use std::path::Path;
use std::result::Result as Result_;
use std::sync::Arc;
use thiserror::Error;

use crate::object::*;
use crate::query::QueryNode;

pub type Result<T, E = StoreError> = Result_<T, E>;

#[derive(Error, Debug)]
pub enum StoreError {
    #[error("could not de/serialize object")]
    Serialization(#[from] serde_json::Error),

    #[error("database error")]
    Sqlite(#[from] rusqlite::Error),

    #[error("invalid usage: {0}")]
    Usage(String),
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

#[derive(Debug)]
enum ChangeType {
    Add,
    Delete,
}

impl rusqlite::ToSql for ChangeType {
    fn to_sql(&self) -> rusqlite::Result<rusqlite::types::ToSqlOutput> {
        match self {
            ChangeType::Add => "add",
            ChangeType::Delete => "delete",
        }
        .to_sql()
    }
}

impl rusqlite::types::FromSql for ChangeType {
    fn column_result(value: rusqlite::types::ValueRef<'_>) -> rusqlite::types::FromSqlResult<Self> {
        match value.as_str()? {
            "add" => Ok(ChangeType::Add),
            "delete" => Ok(ChangeType::Delete),
            _ => Err(rusqlite::types::FromSqlError::InvalidType),
        }
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
            "
                ALTER TABLE checkpoints ADD description TEXT
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
            query: QueryNode::Empty,
        }
    }

    pub fn query(&self, query: impl Into<QueryNode>) -> Collection {
        Collection {
            conn: &self.conn,
            query: query.into(),
        }
    }

    pub fn checkpoint(&mut self) -> Result<Checkpoint<'_>> {
        Checkpoint::new(self)
    }

    pub fn undo(&mut self) -> Result<Option<String>> {
        let transaction = self.conn.transaction()?;

        let (cur_checkpoint_serial, prev_checkpoint_serial) = {
            let last_two_checkpoint_serials: Vec<i64> = transaction
                .prepare(
                    "SELECT serial
                        FROM checkpoints
                        ORDER BY serial DESC
                        LIMIT 2
                    ",
                )?
                .query_and_then(params![], |row| row.get(0).as_store_result())?
                .collect::<Result<_>>()?;

            if last_two_checkpoint_serials.len() == 0 {
                return Ok(None);
            }

            (
                last_two_checkpoint_serials[0],
                *last_two_checkpoint_serials.get(1).unwrap_or(&0),
            )
        };

        let description: String = transaction
            .prepare(
                "SELECT description
                    FROM checkpoints
                    WHERE serial = ?
                ",
            )?
            .query_row(params![cur_checkpoint_serial], |row| row.get(0))?;

        let changes = transaction
            .prepare(
                "SELECT
                    action, object_id, previous
                    FROM object_changes
                    WHERE serial > ?
                    ORDER BY serial DESC
            ",
            )?
            .query_and_then(
                params![prev_checkpoint_serial],
                |row| -> Result<(ChangeType, i64, String)> {
                    Ok((row.get(0)?, row.get(1)?, (row.get(2)?)))
                },
            )?
            .collect::<Result<Vec<_>>>()
            .as_store_result()?;

        for (change_type, object_id, previous_serialized) in changes {
            match change_type {
                ChangeType::Add => assert_eq!(
                    transaction.execute(
                        "DELETE
                            FROM objects
                            WHERE object_id = ?",
                        params![object_id]
                    )?,
                    1
                ),
                ChangeType::Delete => assert_eq!(
                    transaction.execute(
                        "INSERT
                            INTO objects(object_id, properties)
                            VALUES(?, ?)
                        ",
                        params![object_id, previous_serialized]
                    )?,
                    1
                ),
            }
        }

        transaction.execute(
            "DELETE
                FROM object_changes
                WHERE serial > ?
            ",
            params![prev_checkpoint_serial],
        )?;

        transaction.execute(
            "DELETE
                FROM checkpoints
                WHERE serial = ?
            ",
            params![cur_checkpoint_serial],
        )?;

        transaction.commit()?;

        Ok(Some(description))
    }
}

pub struct Checkpoint<'a> {
    store: &'a Store,
    transaction: rusqlite::Transaction<'a>,
}

impl<'a> Checkpoint<'a> {
    fn new(store: &'a mut Store) -> Result<Checkpoint> {
        let transaction = store.conn.unchecked_transaction()?;

        Ok(Checkpoint { store, transaction })
    }

    fn create_checkpoint(&self, description: &str) -> Result<()> {
        self.transaction.execute(
            "INSERT
                INTO checkpoints(serial, description)
                VALUES(
                    (SELECT
                        IFNULL(MAX(serial), 0)
                        FROM object_changes
                    ),
                    ?
                )
            ",
            params![description],
        )?;

        Ok(())
    }

    pub fn commit(self, description: impl AsRef<str>) -> Result<()> {
        self.create_checkpoint(description.as_ref())?;
        self.transaction.commit().as_store_result()
    }

    fn record_change(
        &self,
        change_type: ChangeType,
        object_id: i64,
        previous: impl AsRef<str>,
    ) -> Result<()> {
        self.transaction.execute(
            "INSERT
                INTO object_changes(action, object_id, previous)
                VALUES(?, ?, ?)
            ",
            params![change_type, object_id, previous.as_ref()],
        )?;

        Ok(())
    }

    pub fn add(&self, object: Object) -> Result<i64> {
        let object_serialized = serde_json::to_string(&object)?;

        self.transaction
            .prepare("INSERT INTO objects(properties) VALUES(?)")?
            .execute(params![object_serialized])?;

        let object_id = self.store.conn.last_insert_rowid();
        self.record_change(ChangeType::Add, object_id, "{}")?;

        Ok(object_id as i64)
    }

    pub fn query(&self, query: impl Into<QueryNode>) -> MutableCollection {
        MutableCollection {
            checkpoint: &self,
            collection: Collection {
                conn: &self.transaction,
                query: query.into(),
            },
        }
    }
}

pub struct Collection<'a> {
    conn: &'a Connection,
    query: QueryNode,
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

    pub fn exists(&self) -> Result<bool> {
        Ok(self.len()? != 0)
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

pub struct MutableCollection<'a> {
    checkpoint: &'a Checkpoint<'a>,
    collection: Collection<'a>,
}

impl<'a> MutableCollection<'a> {
    pub fn delete(&self) -> Result<usize> {
        for object in self.iter()? {
            self.checkpoint.record_change(
                ChangeType::Delete,
                object["object-id"].as_number().unwrap(),
                serde_json::to_string(&object)?,
            )?;
        }

        let (mut statement, params) = self.prepare_with_query("DELETE FROM objects")?;
        statement.execute(params).as_store_result()
    }
}

impl<'a> std::ops::Deref for MutableCollection<'a> {
    type Target = Collection<'a>;

    fn deref(&self) -> &Collection<'a> {
        &self.collection
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Q;
    use tempfile::{Builder, TempDir};

    fn open_store<'a>(tempdir: &TempDir, name: &str) -> Store {
        Store::open(tempdir.path().join(name)).unwrap()
    }

    fn test_dir() -> TempDir {
        Builder::new().prefix("qualia-store").tempdir().unwrap()
    }

    fn populated_store() -> Result<(Store, TempDir)> {
        let test_dir = test_dir();
        let mut store = open_store(&test_dir, "store.qualia");

        let checkpoint = store.checkpoint()?;
        checkpoint.add(object!("name" => "one", "blah" => "blah"))?;
        checkpoint.add(object!("name" => "two", "blah" => "halb"))?;
        checkpoint.add(object!("name" => "three", "blah" => "BLAH"))?;
        checkpoint.add(object!("name" => "four", "blah" => "blahblah"))?;
        checkpoint.commit("populate store")?;

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

        assert_eq!(all.len()?, 4);
        let mut all_objects = all.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut all_objects);
        assert_eq!(
            all_objects,
            vec![
                object!("name" => "four", "blah" => "blahblah", "object-id" => 4),
                object!("name" => "one", "blah" => "blah", "object-id" => 1),
                object!("name" => "three", "blah" => "BLAH", "object-id" => 3),
                object!("name" => "two", "blah" => "halb", "object-id" => 2),
            ],
        );

        Ok(())
    }

    #[test]
    fn adding_objects_can_be_undone() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        let object_id = checkpoint.add(object!("name" => "b", "c" => "d"))?;
        checkpoint.commit("add undoable object")?;

        assert!(store.query(Q.id(object_id)).exists()?);
        assert_eq!(store.all().len()?, 5);

        assert_eq!(store.undo()?, Some("add undoable object".to_string()));

        assert!(!store.query(Q.id(object_id)).exists()?);
        assert_eq!(store.all().len()?, 4);

        Ok(())
    }

    #[test]
    fn added_objects_can_be_found() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let found = store.query(QueryNode::PropEqual {
            name: "name".to_string(),
            value: PropValue::String("one".to_string()),
        });

        assert_eq!(found.len()?, 1);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![object!("name" => "one", "blah" => "blah", "object-id" => 1)],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_deleted() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        let object_id = checkpoint.add(object!("name" => "b", "c" => "d"))?;
        checkpoint.commit("add deleteable object")?;

        let checkpoint = store.checkpoint()?;
        checkpoint.query(Q.id(object_id)).delete()?;
        checkpoint.commit("delete deletable object")?;

        assert!(!store.query(Q.id(object_id)).exists()?);
        assert_eq!(store.all().len()?, 4);

        Ok(())
    }

    #[test]
    fn deleting_objects_can_be_undone() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        assert_eq!(checkpoint.query(Q.equal("name", "one")).delete()?, 1);
        checkpoint.commit("remove object one")?;

        assert_eq!(store.undo()?, Some("remove object one".to_string()));

        assert!(store.query(Q.equal("name", "one")).exists()?);
        assert_eq!(store.all().len()?, 4);

        Ok(())
    }

    #[test]
    fn can_undo_to_an_empty_store() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        assert_eq!(store.undo()?, Some("populate store".to_string()));
        assert_eq!(store.all().len()?, 0);

        assert_eq!(store.undo()?, None);

        Ok(())
    }

    #[test]
    fn objects_can_be_found_by_their_object_id() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        let object_id = checkpoint.add(object!("name" => "b", "c" => "d"))?;
        checkpoint.commit("add object for its ID")?;

        let found = store.query(Q.id(object_id));

        assert_eq!(found.len()?, 1);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![object!("name" => "b", "c" => "d", "object-id" => object_id)],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_found_by_like() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let found = store.query(Q.like("blah", "blah"));

        assert_eq!(found.len()?, 2);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![
                object!("name" => "one", "blah" => "blah", "object-id" => 1),
                object!("name" => "three", "blah" => "BLAH", "object-id" => 3)
            ],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_found_by_and() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        let found = store.query(Q.equal("name", "one").equal("blah", "blah"));

        assert_eq!(found.len()?, 1);
        let mut found_objects = found.iter()?.collect::<Vec<Object>>();
        sort_objects(&mut found_objects);
        assert_eq!(
            found_objects,
            vec![object!("name" => "one", "blah" => "blah", "object-id" => 1),],
        );

        Ok(())
    }
}

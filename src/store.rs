use regex::Regex;
use rusqlite::{params, params_from_iter, Connection};
use std::convert::TryInto;
use std::path::Path;
use std::result::Result as Result_;
use std::sync::Arc;
use thiserror::Error;

use crate::object::*;
use crate::query::QueryNode;

pub type CheckpointId = i64;

/// Convenience type for possibly returning a [`StoreError`].
pub type Result<T, E = StoreError> = Result_<T, E>;

/// All errors that may be returned from a [`Store`].
#[derive(Error, Debug)]
pub enum StoreError {
    #[error("could not convert object to shape")]
    Conversion(#[from] ConversionError),

    #[error("could not de/serialize object")]
    Serialization(#[from] serde_json::Error),

    #[error("database error")]
    Sqlite(#[from] rusqlite::Error),

    #[error("invalid usage: {0}")]
    Usage(String),

    #[error("did not find one item, found {0}")]
    NotOne(usize),
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
    Update,
}

impl rusqlite::ToSql for ChangeType {
    fn to_sql(&self) -> rusqlite::Result<rusqlite::types::ToSqlOutput> {
        match self {
            ChangeType::Add => "add",
            ChangeType::Delete => "delete",
            ChangeType::Update => "update",
        }
        .to_sql()
    }
}

impl rusqlite::types::FromSql for ChangeType {
    fn column_result(value: rusqlite::types::ValueRef<'_>) -> rusqlite::types::FromSqlResult<Self> {
        match value.as_str()? {
            "add" => Ok(ChangeType::Add),
            "delete" => Ok(ChangeType::Delete),
            "update" => Ok(ChangeType::Update),
            _ => Err(rusqlite::types::FromSqlError::InvalidType),
        }
    }
}

/// A set of objects stored on disk.
pub struct Store {
    conn: Connection,
}

impl Store {
    /// Open a store at the given path.
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

    /// Get a [`Collection`] of all objects.
    pub fn all(&self) -> Collection {
        Collection {
            conn: &self.conn,
            query: QueryNode::Empty,
        }
    }

    /// Get a [`Collection`] of the objects matching the given query.
    ///
    /// This can take either a [`QueryNode`] or [`QueryBuilder`](crate::query_builder::QueryBuilder); you almost certainly want to use
    /// the latter.
    pub fn query(&self, query: impl Into<QueryNode>) -> Collection {
        Collection {
            conn: &self.conn,
            query: query.into(),
        }
    }

    /// Get a [`CachedMapping`] of the objects matching the given query.
    ///
    /// Objects will be fetched ahead of time.
    pub fn cached_map<F: FnMut(Object, &Store) -> Result<O>, O>(
        &self,
        query: impl Into<QueryNode>,
        f: F,
    ) -> Result<CachedMapping<F, O>> {
        CachedMapping::new(self, query.into(), f)
    }

    /// Start a [`Checkpoint`] on the store. All modifications must be done through a checkpoint.
    ///
    /// This method takes a mutable reference to ensure that only one checkpoint can be active at a given time.
    pub fn checkpoint(&mut self) -> Result<Checkpoint<'_>> {
        Checkpoint::new(self)
    }

    /// Undo all changes in the last checkpoint.
    ///
    /// Returns the description of the undone checkpoint, if any. If no checkpoints exists, returns
    /// [`None`].
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
                ChangeType::Update => assert_eq!(
                    transaction.execute(
                        "UPDATE
                            objects
                            SET properties = ?
                            WHERE object_id = ?
                        ",
                        params![previous_serialized, object_id]
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

    /// Get the ID of the last checkpoint, if any.
    pub fn last_checkpoint_id(&self) -> Result<CheckpointId> {
        let checkpoint_id: i64 = self
            .conn
            .prepare(
                "SELECT checkpoint_id
                    FROM checkpoints
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                ",
            )?
            .query_row(params![], |row| row.get(0))?;

        return Ok(checkpoint_id);
    }

    /// Check if the store has been changed since the given checkpoint.
    pub fn modified_since(&self, a: CheckpointId) -> Result<bool> {
        let b = self.last_checkpoint_id()?;

        return Ok(a != b);
    }
}

/// A set of not-yet-committed changes to a [`Store`], as created by [`Store::checkpoint()`].
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

    /// Commit this transaction with the given description.
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

    /// Add an object to the store.
    ///
    /// Returns the ID of the newly created object.
    pub fn add(&self, object: Object) -> Result<i64> {
        let object_serialized = serde_json::to_string(&object)?;

        self.transaction
            .prepare("INSERT INTO objects(properties) VALUES(?)")?
            .execute(params![object_serialized])?;

        let object_id = self.store.conn.last_insert_rowid();
        self.record_change(ChangeType::Add, object_id, "{}")?;

        Ok(object_id as i64)
    }

    /// Add an object to the store.
    ///
    /// Stores the ID inside the created object.
    pub fn add_with_id<O>(&self, object: &mut O) -> Result<()>
    where
        O: Clone + ObjectShapeWithId + Into<Object>,
    {
        let object_id = self.add(object.clone().into())?;

        object.set_object_id(object_id);

        Ok(())
    }

    /// Get a [`MutableCollection`] of the objects matching the given query.
    ///
    /// This can take either a [`QueryNode`] or [`QueryBuilder`](crate::query_builder::QueryBuilder); you almost certainly want to use
    /// the latter.
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

impl<'a> std::ops::Deref for Checkpoint<'a> {
    type Target = Store;

    fn deref(&self) -> &Store {
        &self.store
    }
}

/// A reference to the set of objects matching a given query, as returned by [`Store::all()`] or
/// [`Store::query()`].
///
/// All actions on a collection are lazy; no queries are run or objects fetched until a method is
/// called. The collection also doesn't hold on to the objects; if any of them are deleted or modified,
/// future calls will return the new state.
///
/// A collection may be used multiple times. For instance, it's valid to call
/// [`.len()`](Collection::len) and
/// [`.iter()`](Collection::iter) on the same [`Collection`] object.
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

    /// Get the number of objects in the collection.
    pub fn len(&self) -> Result<usize> {
        let (mut statement, params) = self.prepare_with_query("SELECT COUNT(*) FROM objects")?;
        Ok(statement
            // This workaround can be removed when https://github.com/rusqlite/rusqlite/issues/700
            // is closed
            .query_row(params_from_iter(params), |row| row.get::<usize, i64>(0))?
            as usize)
    }

    /// Returns true if there are any objects in the collection.
    pub fn exists(&self) -> Result<bool> {
        Ok(self.len()? != 0)
    }

    /// Iterate over all objects in the collection.
    ///
    /// This prefetches all objects in the collection so that errors can be reported early.
    pub fn iter(&self) -> Result<impl Iterator<Item = Object> + 'a> {
        let (mut statement, params) =
            self.prepare_with_query("SELECT object_id, properties FROM objects")?;

        let rows = statement.query_and_then(params_from_iter(params), |row| {
            Ok((row.get::<usize, i64>(0)?, row.get::<usize, String>(1)?))
        })?;

        Ok(rows
            .map(|r: rusqlite::Result<(i64, String)>| {
                r.as_store_result()
                    .and_then(|(object_id, serialized_object)| {
                        let mut object =
                            serde_json::from_str::<Object>(&serialized_object).as_store_result()?;

                        object.insert("object_id".to_string(), PropValue::Number(object_id));
                        Ok(object)
                    })
            })
            .collect::<Result<Vec<Object>>>()?
            .into_iter())
    }

    /// Get one and only one object from the collection.
    ///
    /// Will error if more than one object is returned.
    pub fn one(&self) -> Result<Object> {
        let mut results = self.iter()?;
        let len = self.len()?;

        if len > 1 {
            return Err(StoreError::NotOne(len));
        }

        results.next().ok_or_else(|| StoreError::NotOne(0))
    }

    /// Iterate over all objects in the collection, converting them to the given shape.
    ///
    /// This prefetches all objects in the collection so that errors can be reported early.
    pub fn iter_as<T: ObjectShapePlain + 'a>(&self) -> Result<impl Iterator<Item = T> + 'a> {
        Ok(self
            .iter()?
            .map(|object| object.try_into().as_store_result())
            .collect::<Result<Vec<T>>>()?
            .into_iter())
    }

    /// Get one and only one object from the collection, converting it to the given shape.
    ///
    /// Will error if more than one object is returned.
    pub fn one_as<T: ObjectShapePlain + 'a>(&self) -> Result<T> {
        let mut results = self.iter_as()?;
        let len = self.len()?;

        if len > 1 {
            return Err(StoreError::NotOne(len));
        }

        results.next().ok_or_else(|| StoreError::NotOne(0))
    }

    /// Iterate over all objects in the collection, converting them to the given shape.
    ///
    /// This prefetches all objects in the collection so that errors can be reported early.
    pub fn iter_converted<T: ObjectShape + 'a>(
        &self,
        store: &Store,
    ) -> Result<impl Iterator<Item = T> + 'a> {
        Ok(self
            .iter()?
            .map(|object| T::try_convert(object, store).as_store_result())
            .collect::<Result<Vec<T>>>()?
            .into_iter())
    }

    /// Get one and only one object from the collection, converting it to the given shape.
    ///
    /// Will error if more than one object is returned.
    pub fn one_converted<T: ObjectShape + 'a>(&self, store: &Store) -> Result<T> {
        let mut results = self.iter_converted(&store)?;
        let len = self.len()?;

        if len > 1 {
            return Err(StoreError::NotOne(len));
        }

        results.next().ok_or_else(|| StoreError::NotOne(0))
    }
}

/// A set of results of querying a given query and mapping the results, as returned by [`Store::cached_query()`].
///
/// Objects are fetched ahead of time. To check if the cache is still valid, use
/// [`CachedMapping::valid()`].
pub struct CachedMapping<F, O> {
    fetched_at_checkpoint: CheckpointId,
    query: QueryNode,
    objects: Vec<O>,
    f: F,
}

impl<F, O> CachedMapping<F, O>
where
    F: FnMut(Object, &Store) -> Result<O>,
{
    fn new(store: &Store, query: QueryNode, f: F) -> Result<CachedMapping<F, O>> {
        let mut result = CachedMapping {
            fetched_at_checkpoint: store.last_checkpoint_id()?,
            query: query.clone(),
            objects: vec![],
            f,
        };
        result.refresh(&store)?;

        Ok(result)
    }

    fn refresh(&mut self, store: &Store) -> Result<()> {
        self.objects = store
            .query(self.query.clone())
            .iter()?
            .map(|obj| (self.f)(obj, &store))
            .collect::<Result<Vec<O>>>()?;

        Ok(())
    }

    pub fn refresh_if_needed(&mut self, store: &Store) -> Result<()> {
        if !self.valid(&store)? {
            self.fetched_at_checkpoint = store.last_checkpoint_id()?;
            self.refresh(&store)?;
        }

        Ok(())
    }

    pub fn valid(&self, store: &Store) -> Result<bool> {
        Ok(!store.modified_since(self.fetched_at_checkpoint)?)
    }

    pub fn iter(&self) -> impl Iterator<Item = &O> {
        self.objects.iter()
    }

    pub fn len(&self) -> usize {
        self.objects.len()
    }

    pub fn exists(&self) -> bool {
        self.objects.len() > 0
    }
}

/// A reference to a modifiable set of objects matching a given query, as returned by
/// [`Checkpoint::query()`].
///
/// All methods of [`Collection`] are available for [`MutableCollection`].
pub struct MutableCollection<'a> {
    checkpoint: &'a Checkpoint<'a>,
    collection: Collection<'a>,
}

impl<'a> MutableCollection<'a> {
    /// Delete all objects in the collection.
    ///
    /// Returns the number of deleted objects.
    pub fn delete(&self) -> Result<usize> {
        for object in self.iter()? {
            self.checkpoint.record_change(
                ChangeType::Delete,
                object["object_id"].as_number().unwrap(),
                serde_json::to_string(&object)?,
            )?;
        }

        let (mut statement, params) = self.prepare_with_query("DELETE FROM objects")?;
        statement
            .execute(params_from_iter(params))
            .as_store_result()
    }

    /// Set the given fields on objects in the collection.
    ///
    /// Returns the number of updated objects.
    pub fn set(&self, fields: Object) -> Result<usize> {
        if fields.len() == 0 {
            return Ok(0);
        }

        for object in self.iter()? {
            self.checkpoint.record_change(
                ChangeType::Update,
                object["object_id"].as_number().unwrap(),
                serde_json::to_string(&object)?,
            )?;
        }

        let fields_serialized = serde_json::to_string(&fields)?;

        let (mut statement, mut params) =
            self.prepare_with_query("UPDATE objects SET properties = json_patch(properties, ?)")?;

        params.insert(0, Box::new(fields_serialized) as Box<dyn rusqlite::ToSql>);

        statement
            .execute(params_from_iter(params))
            .as_store_result()
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
    use crate::{ObjectShape, Q};
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
        let store = open_store(&test_dir(), "store.qualia");
        assert_eq!(store.all().len()?, 0);

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
                object!("name" => "four", "blah" => "blahblah", "object_id" => 4),
                object!("name" => "one", "blah" => "blah", "object_id" => 1),
                object!("name" => "three", "blah" => "BLAH", "object_id" => 3),
                object!("name" => "two", "blah" => "halb", "object_id" => 2),
            ],
        );

        Ok(())
    }

    #[test]
    fn added_objects_can_be_retrieved_one_by_one() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        assert_eq!(
            store.query(Q.id(1)).one()?,
            object!("name" => "one", "blah" => "blah", "object_id" => 1),
        );

        assert!(store.query(Q.id(5)).one().is_err());
        assert!(store.query(Q.like("name", "blah")).one().is_err());

        Ok(())
    }

    #[test]
    fn objects_can_be_iterated_as_a_shape() -> Result<()> {
        let (store, _test_dir) = populated_store()?;

        use crate as qualia;
        #[derive(Debug, ObjectShape, PartialEq)]
        struct Blah {
            name: String,
        }

        let mut all_blah: Vec<_> = store.all().iter_as::<Blah>()?.collect();
        all_blah.sort_by_key(|blah| blah.name.clone());

        assert_eq!(
            all_blah,
            vec![
                Blah {
                    name: "four".to_string()
                },
                Blah {
                    name: "one".to_string()
                },
                Blah {
                    name: "three".to_string()
                },
                Blah {
                    name: "two".to_string()
                },
            ],
        );

        assert_eq!(
            store.query(Q.id(1)).one_as::<Blah>()?,
            Blah {
                name: "one".to_string()
            },
        );

        assert!(store.query(Q.id(5)).one_as::<Blah>().is_err());
        assert!(store
            .query(Q.like("name", "blah"))
            .one_as::<Blah>()
            .is_err());

        Ok(())
    }

    #[test]
    fn objects_can_be_inserted_from_a_shape() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        use crate as qualia;
        #[derive(Clone, Debug, ObjectShape, PartialEq)]
        struct ShapeWithId {
            object_id: Option<i64>,
            name: String,
        }

        let mut obj = ShapeWithId {
            object_id: None,
            name: "yo".to_string(),
        };
        let checkpoint = store.checkpoint()?;
        checkpoint.add_with_id(&mut obj)?;
        checkpoint.commit("add undoable object")?;

        assert!(obj.object_id.is_some());
        let object_id = obj.get_object_id().unwrap();

        assert_eq!(
            store.query(Q.id(object_id)).one_as::<ShapeWithId>()?,
            ShapeWithId {
                object_id: Some(object_id),
                name: "yo".to_string()
            },
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
            vec![object!("name" => "one", "blah" => "blah", "object_id" => 1)],
        );

        Ok(())
    }

    #[test]
    fn referenced_objects_can_be_found() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        use crate as qualia;
        #[derive(Clone, Debug, ObjectShape, PartialEq)]
        struct ParentShape {
            object_id: Option<i64>,
        }

        #[derive(Clone, Debug, ObjectShape, PartialEq)]
        struct ShapeWithReferenced {
            object_id: Option<i64>,
            parent_shape: ParentShape,
        }

        let mut parent_shape = ParentShape { object_id: None };
        let checkpoint = store.checkpoint()?;
        checkpoint.add_with_id(&mut parent_shape)?;

        let mut shape_with_related = ShapeWithReferenced {
            object_id: None,
            parent_shape,
        };
        checkpoint.add_with_id(&mut shape_with_related)?;
        checkpoint.commit("add related object")?;

        dbg!(store
            .query(Q.id(shape_with_related.get_object_id().unwrap()))
            .iter_converted::<ShapeWithReferenced>(&store)?
            .collect::<Vec<_>>(),);

        assert_eq!(
            store
                .query(Q.id(shape_with_related.get_object_id().unwrap()))
                .one_converted::<ShapeWithReferenced>(&store)?
                .parent_shape,
            ParentShape {
                object_id: shape_with_related.parent_shape.object_id,
            },
        );

        Ok(())
    }

    #[test]
    fn can_cache_queries() -> Result<()> {
        use crate as qualia;
        #[derive(Debug, ObjectShape, PartialEq)]
        struct Blah {
            name: String,
        }

        let (mut store, _test_dir) = populated_store()?;

        let mut cached_one_to_one = store.cached_map(Q.equal("blah", "blah"), |x, _| Ok(x))?;

        assert_eq!(
            cached_one_to_one.iter().collect::<Vec<_>>(),
            vec![&object!("name" => "one", "blah" => "blah", "object_id" => 1)]
        );
        assert_eq!(cached_one_to_one.len(), 1);
        assert_eq!(cached_one_to_one.exists(), true);
        assert_eq!(cached_one_to_one.valid(&store)?, true);

        let checkpoint = store.checkpoint()?;
        checkpoint.add(object!("name" => "five", "blah" => "blah"))?;
        checkpoint.commit("add new object")?;

        assert_eq!(cached_one_to_one.len(), 1);
        assert_eq!(cached_one_to_one.exists(), true);
        assert_eq!(
            cached_one_to_one.iter().collect::<Vec<_>>(),
            vec![&object!("name" => "one", "blah" => "blah", "object_id" => 1)]
        );
        assert_eq!(cached_one_to_one.valid(&store)?, false);

        cached_one_to_one.refresh_if_needed(&store)?;
        assert_eq!(cached_one_to_one.len(), 2);
        assert_eq!(cached_one_to_one.exists(), true);
        assert_eq!(
            cached_one_to_one.iter().collect::<Vec<_>>(),
            vec![
                &object!("name" => "one", "blah" => "blah", "object_id" => 1),
                &object!("name" => "five", "blah" => "blah", "object_id" => 5),
            ]
        );
        assert_eq!(cached_one_to_one.valid(&store)?, true);

        let checkpoint = store.checkpoint()?;
        checkpoint.query(Q.equal("blah", "blah")).delete()?;
        checkpoint.commit("delete cached objects")?;

        assert_eq!(cached_one_to_one.len(), 2);
        assert_eq!(cached_one_to_one.exists(), true);
        assert_eq!(
            cached_one_to_one.iter().collect::<Vec<_>>(),
            vec![
                &object!("name" => "one", "blah" => "blah", "object_id" => 1),
                &object!("name" => "five", "blah" => "blah", "object_id" => 5),
            ]
        );
        assert_eq!(cached_one_to_one.valid(&store)?, false);

        cached_one_to_one.refresh_if_needed(&store)?;

        assert_eq!(cached_one_to_one.len(), 0);
        assert_eq!(cached_one_to_one.exists(), false);
        assert_eq!(
            cached_one_to_one.iter().collect::<Vec<_>>(),
            Vec::<&Object>::new()
        );
        assert_eq!(cached_one_to_one.valid(&store)?, true);

        let cached_extracted_fields = store.cached_map(Q.equal("blah", "halb"), |o, store| {
            Ok(Blah::try_convert(o, &store)?.name)
        })?;
        assert_eq!(
            cached_extracted_fields.iter().collect::<Vec<_>>(),
            vec!["two"],
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
            vec![object!("name" => "b", "c" => "d", "object_id" => object_id)],
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
                object!("name" => "one", "blah" => "blah", "object_id" => 1),
                object!("name" => "three", "blah" => "BLAH", "object_id" => 3)
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
            vec![object!("name" => "one", "blah" => "blah", "object_id" => 1),],
        );

        Ok(())
    }

    #[test]
    fn objects_can_be_modified() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        assert_eq!(checkpoint.query(Q.id(1)).set(object!("name" => "wun"))?, 1);
        checkpoint.commit("change 1")?;

        assert_eq!(
            store.query(Q.id(1)).iter()?.collect::<Vec<Object>>(),
            vec![object!("name" => "wun", "blah" => "blah", "object_id" => 1)],
        );

        Ok(())
    }

    #[test]
    fn objects_modification_can_be_undone() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        assert_eq!(checkpoint.query(Q.id(1)).set(object!("name" => "wun"))?, 1);
        checkpoint.commit("change 1")?;

        store.undo()?;

        assert_eq!(
            store.query(Q.id(1)).iter()?.collect::<Vec<Object>>(),
            vec![object!("name" => "one", "blah" => "blah", "object_id" => 1)],
        );

        Ok(())
    }

    #[test]
    fn checkpoint_ids_expire_with_changes_or_undos() -> Result<()> {
        let (mut store, _test_dir) = populated_store()?;

        let checkpoint = store.checkpoint()?;
        assert_eq!(checkpoint.query(Q.id(1)).set(object!("name" => "wun"))?, 1);
        checkpoint.commit("change 1")?;

        let before_change_checkpoint_id = store.last_checkpoint_id()?;

        let checkpoint = store.checkpoint()?;
        assert_eq!(checkpoint.query(Q.id(1)).set(object!("name" => "wan"))?, 1);
        checkpoint.commit("change 2")?;
        assert!(store.modified_since(before_change_checkpoint_id)?);

        let before_undo_checkpoint_id = store.last_checkpoint_id()?;

        store.undo()?;
        assert!(store.modified_since(before_undo_checkpoint_id)?);

        Ok(())
    }
}

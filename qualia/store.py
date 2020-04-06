# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
#
# Qualia is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Qualia is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Qualia. If not, see <http://www.gnu.org/licenses/>.

from .lazy_import import lazy_import
from .import common

lazy_import(globals(), """
	import json
	import sqlite3
""")

## Initialization

def open(*args, **kwargs):
	return Store(*args, **kwargs)

## Store
# Root of a Qualia object store.

class Store:
	def __init__(self, db_path, read_only = False):
		self.db = sqlite3.connect(
			'file:' + db_path + ('?mode=ro' if read_only else ''),
			uri = True,
			# This will use the column types (not much more than a hint to SQLite) to do conversion
			# to and from Python types.
			detect_types = sqlite3.PARSE_DECLTYPES
		)
		# Make SQLite use a write-ahead instead of a delete-based journal; see
		# [the SQLite documentation](https://www.sqlite.org/wal.html) for more info.
		self.db.execute('PRAGMA journal_mode=WAL')

		# Check that the JSON1 extension is working.
		self.db.execute('SELECT json("{}")')

		# This replaces the usual tuple format for rows with a convenient dict-like object.
		self.db.row_factory = sqlite3.Row
		self._upgrade_if_needed()

		# This indicates whether there have been changes since the last checkpoint.
		self.has_changes = False

	def _upgrade_if_needed(self):
		# We check the version of the database and upgrade it if necessary.
		# Conveniently, this starts at 0 in an empty database.
		version = self.db.execute('PRAGMA user_version').fetchone()[0]

		# We use `AUTOINCREMENT` on the objects table so that IDs are not reused.
		updates = [
			"""
				CREATE TABLE objects (
					object_id INTEGER PRIMARY KEY AUTOINCREMENT,
					properties TEXT
				);
			""",
			"""
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
			""",
		]

		# We set the `user_version` after each update to ensure updates are not applied twice if one
		# in a sequence of updates fails.
		for version, update in enumerate(updates[version:], version + 1):
			self.db.executescript(update)
			self.db.execute("PRAGMA user_version = {}".format(version))

	def _add_change(self, object_id, action, previous):
		self.db.execute(
			'''
				INSERT
					INTO object_changes(object_id, action, previous)
					VALUES(?, ?, ?)
			''',
			(
				object_id,
				action,
				json.dumps(previous),
			)
		)

	def _add_checkpoint(self):
		self.db.execute(
			'''
				INSERT
					INTO checkpoints(serial)
					SELECT
						MAX(serial)
						FROM object_changes
			'''
		)

	def add(self, **properties):
		cur = self.db.execute(
			'''
				INSERT
					INTO objects(properties)
					VALUES(?)
			''',
			(
				json.dumps(properties),
			)
		)

		self._add_change(
			cur.lastrowid,
			'add',
			dict(),
		)

	def _undo_add(self, object_id, previous):
		self.db.execute(
			'''
				DELETE
					FROM objects
					WHERE object_id = ?
			''',
			(
				object_id,
			)
		)

	def _undo_delete(self, object_id, previous):
		self.db.execute(
			'''
				INSERT
					INTO objects(object_id, properties)
					VALUES(?, ?)
			''',
			(
				object_id,
				json.dumps(previous),
			)
		)

	def _undo_update(self, object_id, previous):
		self.db.execute(
			'''
				UPDATE
					objects
					SET properties = ?
					WHERE object_id = ?
			''',
			(
				json.dumps(previous),
				object_id,
			)
		)

	def commit(self):
		self._add_checkpoint()
		self.db.commit()

	def undo(self):
		cur = self.db.execute(f'''
			SELECT
				checkpoint_id, serial
				FROM checkpoints
				ORDER BY checkpoint_id DESC
				LIMIT 2
			''',
		)

		checkpoint_id, end_serial = cur.fetchone() or (None, None)
		_, start_serial = cur.fetchone() or (None, None)

		if end_serial is None:
			# Nothing to do
			return

		if start_serial is None:
			start_serial = 0

		cur = self.db.execute(f'''
			SELECT
				*
				FROM object_changes
				WHERE
					serial > ?
					AND serial <= ?
				ORDER BY serial DESC
			''',
			(
				start_serial,
				end_serial,
			),
		)

		for row in cur.fetchall():
			undo_impl = getattr(self, f'_undo_{row["action"]}')

			undo_impl(row['object_id'], json.loads(row['previous']))

		self.db.execute(f'''
			DELETE
				FROM object_changes
				WHERE
					serial > ?
					AND serial <= ?
			''',
			(
				start_serial,
				end_serial,
			),
		)

		self.db.execute(f'''
			DELETE
				FROM checkpoints
				WHERE
					checkpoint_id = ?
			''',
			(
				checkpoint_id,
			),
		)

		self.db.commit()

	def all(self):
		return StoreSubset(self, {})

	def select(self, **params):
		return StoreSubset(self, params)

	def close(self):
		self.db.close()

class StoreSubset:
	def __init__(self, store, params):
		self.db = store.db
		self.store = store
		self._params = params

		if params:
			self._where_clause = 'WHERE ' + ' AND '.join(
				f'json_extract(properties, "$.{k}") = ?'
				for k in params.keys()
			)
		else:
			self._where_clause = ''

	def _where_query(self, inner_query, *other_params):
		cur = self.db.cursor()
		cur.execute(f'''
			{inner_query}
				{self._where_clause}
			''',
			other_params + tuple(self._params.values()),
		)

		return cur

	def _where_operation(self, action, inner_query, *other_params):
		affected_objects = list(self)

		self._where_query(
			inner_query,
			*other_params
		)

		self._add_multi_changes(action, affected_objects)

	def _add_multi_changes(self, action, affected_objects):
		for object in affected_objects:
			properties = dict(object)
			del properties['object_id']

			self.store._add_change(object['object_id'], action,  properties)

	def delete(self):
		self._where_operation('delete', f'''
			DELETE
				FROM objects
			''',
		)

	def update(self, **new_properties):
		self._where_operation('update', f'''
			UPDATE
				objects
				SET properties = json_patch(properties, ?)
			''',
			json.dumps(new_properties),
		)

	def __iter__(self):
		cur = self._where_query(f'''
			SELECT
				*
				FROM objects
			''',
		)

		for row in cur.fetchall():
			yield dict(json.loads(row['properties']), object_id = row['object_id'])

	def __len__(self):
		cur = self._where_query(f'''
			SELECT
				COUNT(*)
				FROM objects
			''',
		)

		return cur.fetchone()[0]

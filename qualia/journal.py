# This is the implementation of the journal, which allows for recovery and limited undo.
#
## Imports
import base64
import datetime
import pickle
import sqlite3

## Journal
# The journal is implemented on top of a simple SQLite database, which gives us a convenient
# datastore and good disaster resilience.
class Journal:
	def __init__(self, filename):
		self.db = sqlite3.connect(
			filename,
			# This will use the column types (not much more than a hint to SQLite) to do conversion
			# to and from Python types.
			detect_types = sqlite3.PARSE_DECLTYPES
		)
		# Make SQLite use a write-ahead instead of a delete-based journal; see
		# [the SQLite documentation](https://www.sqlite.org/wal.html) for more info.
		self.db.execute('PRAGMA journal_mode=WAL');

		# This replaces the usual tuple format for rows with a convenient dict-like object.
		self.db.row_factory = sqlite3.Row
		self.upgrade_if_needed()

		# This indicates whether there have been changes since the last checkpoint.
		self.has_changes = False

	def upgrade_if_needed(self):
		# We check the version of the database and upgrade it if necessary.
		# Conveniently, this starts at 0 in an empty database.
		version = self.db.execute('PRAGMA user_version').fetchone()[0]

		updates = [
			"""
				CREATE TABLE journal (
					serial INTEGER PRIMARY KEY,
					timestamp TIMESTAMP,
					source TEXT,
					file TEXT,
					op TEXT,
					extra BLOB
				);
			""",
			"""
				CREATE TABLE checkpoints (
					checkpoint_id INTEGER PRIMARY KEY,
					timestamp TIMESTAMP,
					serial INTEGER
				);
			"""
		]

		# We set the `user_version` after each update to ensure updates are not applied twice if one
		# in a sequence of updates fails.
		for version, update in enumerate(updates[version:], version + 1):
			self.db.executescript(update)
			self.db.execute("PRAGMA user_version = {}".format(version))
	
	# Appends a new entry to the journal. Any extra args are usually specific to the given `op`, and
	# will be pickled before storage.
	def append(self, source, file, op, *args, time = None):
		cur = self.db.cursor()
		cur.execute('''
			INSERT INTO
				journal(timestamp, source, file, op, extra)
				VALUES(?, ?, ?, ?, ?)
			''',
			(time or datetime.datetime.now(), source, file, op, pickle.dumps(args))
		)
		self.db.commit()
		self.has_changes = True

	# Returns all matching transactions for a given file and op.
	def get_transactions(self, file, op):
		cur = self.db.cursor()
		cur.execute('''
			SELECT
				*
				FROM journal
				WHERE file = ? AND op = ?
				ORDER BY serial
			''',
			(file, op)
		)

		for row in cur.fetchall():
			yield dict(row, extra = pickle.loads(row['extra']))

	# Sets a checkpoint at the current journal point. This groups all the transactions since the
	# last checkpoint into one operation and marks them as completely applied to the other
	# components of the database.
	#
	# If no transactions have been done since the last checkpoint, no checkpoint will be created and
	# this method will return `None`.
	def checkpoint(self, time = None):
		if not self.has_changes: return None

		cur = self.db.cursor()
		cur.execute('''
			INSERT INTO
				checkpoints(timestamp, serial)
				VALUES(?, (SELECT MAX(serial) FROM journal))
			''',
			(time or datetime.datetime.now(),)
		)
		self.db.commit()

		return cur.lastrowid

	# Retrieves the given checkpoint and its transactions. (If `None`, retrieves the latest
	# transaction.) 
	def get_checkpoint(self, checkpoint_id):
		if checkpoint_id is None:
			checkpoint = self.db.execute('''
					SELECT
					*
					FROM checkpoints
					ORDER BY checkpoint_id DESC
					LIMIT 1
				''').fetchone()
		else:
			checkpoint = self.db.execute('''
				SELECT
					*
					FROM checkpoints
					WHERE checkpoint_id = ?
				''',
				(checkpoint_id,)
			).fetchone()
		if not checkpoint: return None

		last_checkpoint = self.db.execute('''
			SELECT
				serial
				FROM checkpoints
				WHERE checkpoint_id < ?
				ORDER BY checkpoint_id DESC
				LIMIT 1
			''',
			(checkpoint['checkpoint_id'],)
		).fetchone()

		checkpoint = dict(checkpoint)
		checkpoint.update(
			transactions = [
				dict(row, extra = pickle.loads(row['extra']))
				for row in
				self.db.execute('''
					SELECT *
						FROM journal
						WHERE serial > ? AND serial <= ?
						ORDER BY serial
					''',
					(last_checkpoint[0] if last_checkpoint else 0, checkpoint['serial'])
				).fetchall()
			]
		)

		return checkpoint

	# Retrieves the IDs of all checkpoints in the given order (`'asc'` or `'desc'`).
	def all_checkpoint_ids(self, *, order = 'asc'):
		for row in self.db.execute('SELECT checkpoint_id FROM checkpoints ORDER BY checkpoint_id ' + ('DESC' if order == 'desc' else 'ASC')).fetchall():
			yield row[0]

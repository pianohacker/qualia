import base64
import datetime
import pickle
import sqlite3

class Journal:
	def __init__(self, filename):
		self.db = sqlite3.connect(
			filename,
			detect_types = sqlite3.PARSE_DECLTYPES
		)
		self.db.row_factory = sqlite3.Row
		self.upgrade_if_needed()
		self.f = open(filename, 'ab')
		self.has_changes = False

	def upgrade_if_needed(self):
		# Make SQLite use a write-ahead instead of a delete-based journal; see
		# https://www.sqlite.org/wal.html for more info.
		self.db.execute('PRAGMA journal_mode=WAL;');
		version = self.db.execute('PRAGMA user_version').fetchone()[0]

		if version < 1:
			self.db.executescript("""
				CREATE TABLE journal (
					serial INTEGER PRIMARY KEY,
					timestamp TIMESTAMP,
					source TEXT,
					file TEXT,
					op TEXT,
					extra BLOB
				);
			""")

		if version < 2:
			self.db.executescript("""
				CREATE TABLE checkpoints (
					checkpoint_id INTEGER PRIMARY KEY,
					timestamp TIMESTAMP,
					serial INTEGER
				);
			""")

		self.db.execute("PRAGMA user_version = 2")
	
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

	def all_checkpoint_ids(self):
		for row in self.db.execute('SELECT checkpoint_id FROM checkpoints ORDER BY checkpoint_id DESC').fetchall():
			yield row[0]

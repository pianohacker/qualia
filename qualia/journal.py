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
		self.upgrade_if_needed()
		self.f = open(filename, 'ab')

	def upgrade_if_needed(self):
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

			self.db.execute("PRAGMA user_version = 1")
	
	def append(self, source, file, op, *args, time = None):
		cur = self.db.cursor()

		cur.execute('''
			INSERT INTO
				journal(timestamp, source, file, op, extra)
				VALUES(?, ?, ?, ?, ?)
		''', (time or datetime.datetime.now(), source, file, op, pickle.dumps(args)))
		self.db.commit()

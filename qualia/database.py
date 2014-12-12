import codecs
import datetime
import glob
import hashlib
import itertools
import os
from os import path
import shutil
import stat

from . import common, config, journal, search

VERSION = 1

def get_default_path():
	return path.expanduser('~/q')

class File:
	def __init__(self, db, hash, metadata):
		self.db = db
		self.hash = hash
		self.metadata = metadata
		self.metadata.setdefault('hash', hash)
		self.modifications = []

	@property
	def short_hash(self):
		return self.db.get_shortest_hash(self.hash)

	def set_metadata(self, field, value, source = 'user'):
		if field not in self.db.state['metadata']:
			raise common.FieldDoesNotExistError(field)

		if field in self.metadata and self.db.state['metadata'][field]['read-only']:
			raise common.FieldReadOnlyError(field)

		self.metadata[field] = value
		self.modifications.append((source, field, value))

	def __repr__(self):
		return 'qualia.database.File(..., {!r}, {{...}})'.format(self.hash)

class Database:
	def __init__(self, db_path):
		self.db_path = db_path
		self.init_if_needed()
		self.state = {}
		config.load(path.join(self.db_path, 'db_state.yaml'), self.state, config.DB_STATE_BASE)

		if self.state['version'] is None:
			self.state['version'] = VERSION
		elif self.state['version'] != VERSION:
			raise RuntimeError('Cannot open database of version {} (only support version {})'.format(self.state['version'], VERSION))

		self.journal = journal.Journal(path.join(self.db_path, 'journal'))
		self.searchdb = search.SearchDatabase(self, path.join(self.db_path, 'search'))

	def close(self):
		config.save(os.path.join(self.db_path, 'db_state.yaml'), self.state, config.DB_STATE_BASE)

	def init_if_needed(self):
		if not path.exists(self.db_path):
			os.mkdir(self.db_path)
			os.mkdir(path.join(self.db_path, 'files'))
			os.mkdir(path.join(self.db_path, 'search'))

	def get_directory_for_hash(self, hash):
		return path.join(self.db_path, 'files', hash[0:2])

	def get_filename_for_hash(self, hash):
		return path.join(self.get_directory_for_hash(hash), hash)
	
	def add_file(self, source_file, move = False, source = 'user'):
		hash = hashlib.sha512(source_file.read()).hexdigest()
		source_file.seek(0)

		os.makedirs(self.get_directory_for_hash(hash), exist_ok = True)
		filename = self.get_filename_for_hash(hash)

		if path.exists(filename):
			raise common.FileExistsError(hash)

		self.journal.append(source, hash, 'create')

		self.searchdb.add(hash)

		if move:
			try:
				os.rename(source_file.name, filename)
			except OSError:
				shutil.copyfileobj(source_file, open(filename, 'wb'))
				os.unlink(source_file.name)
		else:
			# Cannot use os.link, as the source file can be silently modified, thus corrupting our
			# copy
			shutil.copyfileobj(source_file, open(filename, 'wb'))

		# This is apparently the required song and dance to get the current umask.
		old_umask = os.umask(0)
		os.umask(old_umask)

		os.chmod(filename, (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH) & ~old_umask)

		return File(self, hash, {})

	def add(self, source_filename, *args, **kwargs):
		return self.add_file(open(source_filename, 'rb'), *args, **kwargs)

	def restore_metadata(self, f, only_auto = True):
		modifications = {}

		for transaction in self.journal.get_transactions(f.hash, 'set'):
			if only_auto and transaction['source'] == 'auto': continue

			field, value = transaction['extra']

			modifications[field] = transaction['source'], field, value

		for source, field, value in modifications.items():
			f.set_metadata(field, value, source = source)

	def find_hashes(self, prefix):
		# Note: this is a bit of a hack. Here be dragons.
		# TODO: Remove dragons
		for filename in glob.iglob(self.get_filename_for_hash(prefix + '*')):
			yield path.basename(filename)
	
	def get_shortest_hash(self, hash):
		baselen = 8

		while True:
			result = self.find_hashes(hash[:baselen])
			_, extra = next(result, None), next(result, None)

			if extra is None: break
			baselen += 2

		return hash[:baselen]

	def get_filename(self, f):
		return self.get_filename_for_hash(f.hash)

	def all(self):
		for dir in sorted(os.listdir(path.join(self.db_path, 'files'))):
			for hash in sorted(os.listdir(path.join(self.db_path, 'files', dir))):
				yield File(self, hash, self.searchdb.get(hash))

	def get(self, short_hash):
		result = self.find_hashes(short_hash)
		hash, extra = next(result, None), next(result, None)

		if hash is None:
			raise common.FileDoesNotExistError(short_hash)

		if extra is not None:
			raise common.AmbiguousHashError(short_hash)

		return File(self, hash, self.searchdb.get(hash))

	def delete(self, f, source = 'user'):
		self.journal.append(source, f.hash, 'delete')
		os.unlink(self.get_filename_for_hash(f.hash))
		self.searchdb.delete(f)

		try:
			self.rmdir(self.get_directory_for_hash(f.hash))
		except OSError:
			pass

	def save(self, f):
		t = datetime.datetime.now()
		for source, field, value in f.modifications:
			self.journal.append(source, f.hash, 'set', field, value, time = t)

		self.searchdb.save(f)

		f.modifications = []

	def search(self, query, limit = 10):
		for result in self.searchdb.search(query, limit = limit):
			yield File(self, result['hash'], result)

from . import journal

import codecs
import datetime
import glob
import hashlib
import itertools
import os
from os import path
import shutil

def get_default_path():
	return path.expanduser('~/q')

class File:
	def __init__(self, hash, metadata):
		self.hash = hash
		self.metadata = metadata
		self.modifications = []

	@property
	def short_hash(self):
		return self.hash[0:8]

	def set_metadata(self, key, value, source = 'user'):
		self.metadata[key] = value
		self.modifications.append((source, key, value))
	
	def import_fs_metadata(self, filename):
		self.set_metadata('filename', path.abspath(filename), 'auto')

class AmbiguousHashError(Exception):
	pass

class FileDoesNotExistError(Exception):
	pass

class FileExistsError(Exception):
	pass

class Database:
	def __init__(self, db_path):
		self.db_path = db_path
		self.init_if_needed()
		self.journal = journal.Journal(path.join(self.db_path, 'journal'))

	def init_if_needed(self):
		if not path.isdir(self.db_path):
			os.mkdir(self.db_path)
			os.mkdir(path.join(self.db_path, 'files'))

	def get_directory_for_hash(self, hash):
		return path.join(self.db_path, 'files', hash[0:2])

	def get_filename_for_hash(self, hash):
		return path.join(self.get_directory_for_hash(hash), hash)
	
	def add_file(self, source_file, move = False):
		hash = hashlib.sha512(source_file.read()).hexdigest()
		source_file.seek(0)

		os.makedirs(self.get_directory_for_hash(hash), exist_ok = True)
		filename = self.get_filename_for_hash(hash)

		if path.exists(filename):
			raise FileExistsError(hash)

		self.journal.append('auto', hash, 'create')

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

		return File(hash, {})

	def add(self, source_filename):
		return self.add_file(open(source_filename, 'rb'))

	def find_hashes(self, prefix):
		# Note: this is a bit of a hack. Here be dragons.
		# TODO: Remove dragons
		for filename in glob.iglob(self.get_filename_for_hash(prefix + '*')):
			yield path.basename(filename)

	def get(self, short_hash):
		result = self.find_hashes(short_hash)

		try:
			hash = next(result)
		except StopIteration:
			raise FileDoesNotExistError(short_hash)

		if next(result, None):
			raise AmbiguousHashError(short_hash)

		return File(hash, {})

	def delete(self, f):
		self.journal.append('auto', hash, 'delete')
		self.unlink(self.get_filename_for_hash(hash))

		try:
			self.rmdir(self.get_directory_for_hash(hash))
		except OSError:
			pass

	def save(self, f):
		t = datetime.datetime.now()
		for source, key, value in f.modifications:
			self.journal.append(source, f.hash, 'set', key, value, time = t)

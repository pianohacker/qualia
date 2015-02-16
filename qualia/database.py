# Copyright (c) 2015 Jesse Weaver.
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

## Imports
from .lazy_import import lazy_import
from . import common, config, journal, search

lazy_import(globals(), """
	import codecs
	import datetime
	import glob
	import hashlib
	import itertools
	import os
	from os import path
	import shutil
	import stat
	import string
	import tempfile
""")

## Constants
# Each major database revision has a version number; we're currently only on version 1, but this
# might be needed for sanity checking in the future. It's stored in the `state` file for now.

VERSION = 1

## Utility functions
# Get the default database location, respecting the default or any user-configured XDG data
# directories.
#
# TODO: Make this auto create ~/.local and ~/.local/share if needed.
def get_default_path():
	return path.join(os.environ.get('XDG_DATA_HOME', path.expanduser('~/.local/share')), 'qualia')

# This checks that the hash contains only valid characters and normalizes it to lowercase.
def _validate_hash(hash):
	if set(hash) - set(string.hexdigits):
		raise ValueError(hash)

	return hash.lower()

## File
# This class is the core container for all files within a database.
#
# Design notes: an instance of a file is always assumed to correlate to a valid and existing file
# within the database, and any `File` objects for deleted objects should be quickly deleted. Also,
# this class contains no intelligence or database manipulation methods; all such code should be in
# the `Database` class.
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
		if field not in self.db.fields:
			raise common.FieldDoesNotExistError(field)

		if field in self.metadata and self.db.fields[field]['read-only']:
			raise common.FieldReadOnlyError(field)

		self.modifications.append((source, field, self.metadata.get(field), value))

		if value is None:
			# Don't raise a spurious KeyError if the key does not exist.
			self.metadata.pop(field, None)
		else:
			self.metadata[field] = value

	# The `__repr__` of a `File` only shows its hash, as any useful information about the `Database`
	# or metadata would be too long to be practical.
	def __repr__(self):
		return 'qualia.database.File(..., {!r}, {{...}})'.format(self.hash)

## Database
# This is the core database class, and contains most code that operates directly on the set of
# stored files as well as serving as an intermediary to the journal and search index.
class Database:
	def __init__(self, db_path, read_only = False):
		self.db_path = db_path
		self.read_only = read_only
		self.init_if_needed()

		# First, we load the DB state file...
		self.state = config.load(path.join(self.db_path, 'state'), config.DB_STATE_BASE)
		# Then we take the fields configuration from the global config and overlay it on the
		# fields configuration from the state.
		#
		# This song and dance is necessary because the underlying search storage requires some
		# notification of new fields, and cannot change the type of existing fields.
		self.fields = config.load_value(config.conf['fields'], config.DB_STATE_BASE['fields'], start = self.state['fields'], known_only = True)

		# Then we do some simple version checking.
		if self.state['version'] is None:
			self.state['version'] = VERSION
		elif self.state['version'] != VERSION:
			raise RuntimeError('Cannot open database of version {} (only support version {})'.format(self.state['version'], VERSION))

		self.journal = journal.Journal(path.join(self.db_path, 'journal'), read_only = read_only)
		self.searchdb = search.SearchDatabase(self, path.join(self.db_path, 'search'), read_only = read_only)

	# This should be called once the UI is done with the database.
	#
	# Currently, this only saves the `state`, as the journal and search index are only kept open for
	# long enough to make changes.
	def close(self):
		if not self.read_only:
			config.save(os.path.join(self.db_path, 'state'), self.state, config.DB_STATE_BASE)
	
	# Internal convenience function to raise an error if database is read-only.
	def _require_read_write(self):
		if self.read_only: raise common.DatabaseReadOnlyError()

	# Just a utility method for `__init__`.
	def init_if_needed(self):
		if not path.exists(self.db_path):
			if self.read_only: raise RuntimeError('Database does not exist, cannot create in read_only mode')

			os.mkdir(self.db_path)
			os.mkdir(path.join(self.db_path, 'files'))
			os.mkdir(path.join(self.db_path, 'search'))

	# These translate hashes to the full path on disk where the files are stored.
	def get_directory_for_hash(self, hash):
		return path.join(self.db_path, 'files', hash[0:2])

	def get_filename_for_hash(self, hash):
		return path.join(self.get_directory_for_hash(hash), hash)
	
	### Manipulation
	def add_file(self, source_file, move = False, source = 'user'):
		self._require_read_write()

		def _prepare_filename(hash):
			if self.exists(hash):
				raise common.FileExistsError(hash)

			# While `makedirs` isn't strictly necessary in the current arrangement, it is useful
			# future-proofing for a more deeply nested storage structure.
			os.makedirs(self.get_directory_for_hash(hash), exist_ok = True)
			filename = self.get_filename_for_hash(hash)

			return filename

		copy = not move

		if move:
			try:
				hash = hashlib.sha512(source_file.read()).hexdigest()
				filename = _prepare_filename(hash)
				os.rename(source_file.name, filename)
			except OSError:
				copy = True

		# While technically, we could just grab the hash, seek to the beginning of the file, then
		# copy the file, we do it this more complicated way for two reasons:
		#
		#   1. It's more efficient (though not by much on an SSD).
		#   2. Adding files from a compressed import tarball is abysmallly slow if you seek.
		#
		if copy:
			hashobj = hashlib.sha512()

			try:
				tmp_file = tempfile.NamedTemporaryFile(dir = path.join(self.db_path, 'files'), delete = False)
				chunk = source_file.read(16384)
				while chunk:
					hashobj.update(chunk)
					tmp_file.write(chunk)
					chunk = source_file.read(16384)

				tmp_file.flush()
				hash = hashobj.hexdigest()
				filename = _prepare_filename(hash)
				os.rename(tmp_file.name, filename)
			except:
				# We have to do this manually, as we don't want the file to be deleted if we succeed
				# and it gets renamed.
				os.unlink(tmp_file.name)
				raise

			if move:
				os.unlink(source_file.name)

		self.journal.append(source, hash, 'add')
		self.searchdb.add(hash)

		# This is apparently the required song and dance to get the current umask.
		old_umask = os.umask(0)
		os.umask(old_umask)

		# We then use the umask to mask out any undesired bits from our default permissions, which
		# are `r--r--r--`. The files are marked read-only in order to emphasize their immutability
		# and strong tie to their hash.
		os.chmod(filename, (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH) & ~old_umask)

		return File(self, hash, {})

	def add(self, source_filename, *args, **kwargs):
		return self.add_file(open(source_filename, 'rb'), *args, **kwargs)

	# This restores the most recent version of metadata from the journal for the given hash. 
	#
	# By default, it does not do so for automatically-added metadata, assuming that it will be
	# automatically added with equal or better quality.
	def restore_metadata(self, f, no_auto = True):
		self._require_read_write()

		modifications = {}

		# To save a little bit of thrashing, we go through the transactions (implicitly assumed to
		# be in order) and find the most recent version of the metadata.
		for transaction in self.journal.get_transactions(f.hash, 'set'):
			if no_auto and transaction['source'] == 'auto': continue

			field, value = transaction['extra']

			modifications[field] = transaction['source'], field, value

		for source, field, value in modifications.items():
			f.set_metadata(field, value, source = source)

	# This gives all of the hashes that start with a given prefix.
	def find_hashes(self, prefix):
		prefix = _validate_hash(prefix)

		return self.searchdb.find_hashes(prefix)
	
	# This gets the shortest unambiguous shortened version of the given hash.
	def get_shortest_hash(self, hash):
		# 4 seems to be a decent compromise between making short hashes that will stay unambiguous
		# for some time but are not too short.
		baselen = 4

		while True:
			# This is a bit ugly, but basically gets the first two results from the iterator
			# returned by `find_hashes`. If it gets a second result, the prefix is ambiguous.
			result = self.find_hashes(hash[:baselen])
			_, extra = next(result, None), next(result, None)

			if extra is None: break
			baselen += 2

		return hash[:baselen]

	# Just a quick convenience method.
	def get_filename(self, f):
		return self.get_filename_for_hash(f.hash)

	# Returns a generator giving all the file objects that exist in the database.
	def all(self):
		for metadata in self.searchdb.all():
			yield File(self, metadata['hash'], metadata)

	# Gets the `File` object for a given short hash.
	def get(self, short_hash):
		result = self.find_hashes(short_hash)
		hash, extra = next(result, None), next(result, None)

		if hash is None:
			raise common.FileDoesNotExistError(short_hash)

		if extra is not None:
			raise common.AmbiguousHashError(short_hash)

		return File(self, hash, self.searchdb.get(hash))

	# Deletes both the underlying file and metadata for a given file.
	#
	# TODO: Make this atomic; currently, if a user deletes a set of files and it fails halfway
	# through, the search database and journal will be consistent but some of the actual files will
	# be deleted. This will likely require postponing the actual unlink until some kind of GC phase.
	def delete(self, f, source = 'user'):
		self._require_read_write()

		self.journal.append(source, f.hash, 'delete')
		os.unlink(self.get_filename_for_hash(f.hash))
		self.searchdb.delete(f)

		try:
			os.rmdir(self.get_directory_for_hash(f.hash))
		except OSError:
			pass

	# Saves all the metadata for a given file.
	def save(self, f):
		self._require_read_write()

		t = datetime.datetime.now()
		for source, field, old_value, value in f.modifications:
			self.journal.append(source, f.hash, 'set', field, old_value, value, time = t)

		self.searchdb.save(f)

		f.modifications = []

	# Runs a search against the database and returns a generator with results.
	#
	# This iterator should always be read to completion; otherwise the search database is held open.
	def search(self, query, limit = 10):
		for result in self.searchdb.search(query, limit = limit):
			yield File(self, result['hash'], result)

	# Set a checkpoint, grouping together a set of individual transactions as a single operation.
	def commit(self):
		self.searchdb.commit()

		return self.journal.commit()

	# Undo a given checkpoint (can be `None` to undo the latest).
	def undo(self, checkpoint_id):
		self._require_read_write()

		# We can currently only undo `add`s and `set`s; `delete`s are impossible by definition.
		CAN_UNDO = set(['add', 'set'])

		# Retrieve the checkpoint and make sure that we can undo all of its transactions.
		checkpoint = self.journal.get_checkpoint(checkpoint_id)
		if checkpoint is None: raise common.CheckpointDoesNotExistError(checkpoint_id)

		for transaction in checkpoint['transactions']:
			if transaction['op'] not in CAN_UNDO: raise common.UndoFailedError(transaction)

		# Undo each all transactions for each file in order. We also sort on operation, which
		# coincidentally means that we can undo `add`s before trying to undo any relevant `set`s.
		for hash, transactions in itertools.groupby(sorted(checkpoint['transactions'], key = lambda t: (t['file'], t['op'])), key = lambda t: t['file']):
			f = self.get(hash)

			for transaction in transactions:
				if transaction['op'] == 'add':
					self.delete(f)
					# There's no reason to do anything else once we've deleted the file.
					break
				elif transaction['op'] == 'set':
					field, old_value, value = transaction['extra']
					f.set_metadata(field, old_value)
			else:
				self.save(f)

	# Retrieve all checkpoints (with transactions). `order` can be set to `'asc'` or `'desc'`.
	def all_checkpoints(self, *, order = 'asc'):
		for checkpoint_id in self.journal.all_checkpoint_ids(order = order):
			yield self.journal.get_checkpoint(checkpoint_id)

	# Check to see whether a file exists. We do this using the searchdb rather than the existing
	# files because the searchdb is more likely to be internally consistent.
	def exists(self, hash):
		return self.searchdb.exists(hash)

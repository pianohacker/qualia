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
from . import config, common

lazy_import(globals(), """
	import copy
	import sys
	from whoosh import analysis, fields, index, qparser, query, writing
""")

## Utility functions
# Creates the underlying Whoosh field given the configuration for the given field.
def _create_field_type(field_config):
	return dict(
		datetime = fields.DATETIME(stored = True),
		exact_text = fields.ID(stored = True),
		id = fields.ID(unique = True, stored = True),
		keyword = fields.KEYWORD(stored = True),
		number = fields.NUMERIC(stored = True),
		text = fields.TEXT(analyzer = analysis.StemmingAnalyzer(), stored = True),
	)[field_config['type'].replace('-', '_')]

# This plugin for the Whoosh query parser allows field aliases to be correctly interpreted.
# It is defined in a roundabout way to avoid importing whoosh early.
def _FieldAliasPlugin(map):
	class _FieldAliasPlugin(qparser.Plugin):
		# Based on whoosh.qparser.CopyFieldPlugin, which has the following license:
		#
		#> Copyright 2011 Matt Chaput. All rights reserved.
		#>
		#> Redistribution and use in source and binary forms, with or without
		#> modification, are permitted provided that the following conditions are met:
		#>
		#>    1. Redistributions of source code must retain the above copyright notice,
		#>       this list of conditions and the following disclaimer.
		#>
		#>    2. Redistributions in binary form must reproduce the above copyright
		#>       notice, this list of conditions and the following disclaimer in the
		#>       documentation and/or other materials provided with the distribution.
		#>
		#> THIS SOFTWARE IS PROVIDED BY MATT CHAPUT ``AS IS'' AND ANY EXPRESS OR
		#> IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
		#> MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
		#> EVENT SHALL MATT CHAPUT OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
		#> INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
		#> LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
		#> OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
		#> LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
		#> NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
		#> EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
		#>
		#> The views and conclusions contained in the software and documentation are
		#> those of the authors and should not be interpreted as representing official
		#> policies, either expressed or implied, of Matt Chaput.
		def __init__(self, map):
			self.map = map

		def filters(self, parser):
			# Run after the fieldname filter (100) but before multifield (110)
			return [(self.do_fieldalias, 109)]

		def do_fieldalias(self, parser, group):
			map = self.map
			newgroup = group.empty_copy()
			for node in group:
				if isinstance(node, qparser.syntax.GroupNode):
					# Recurse into groups
					node = self.do_fieldalias(parser, node)
				elif node.has_fieldname:
					fname = node.fieldname or parser.fieldname
					if fname in map:
						node = copy.copy(node)
						node.set_fieldname(map[fname], override=True)
				newgroup.append(node)
			return newgroup

	return _FieldAliasPlugin(map)

## Search database
# This DB serves two purposes in Qualia: it keeps an index of all the metadata contents to allow
# for quick searching, and serves as an easy way to get the latest metadata for a given file.
class SearchDatabase:
	def __init__(self, db, base_path, read_only = False):
		self.db = db
		self.read_only = read_only

		# First, load all the actually configured fields.
		self.configured_fields = {field: _create_field_type(value) for field, value in self.db.fields.items()}

		# Then, depending on whether the database has been previously set up, we either:
		if index.exists_in(base_path):
			# a) check to make sure that any previously configured fields have not been changed.
			self.index = index.open_dir(base_path)

			for name, field in self.index.schema.items():
				if (name not in self.configured_fields or field != self.configured_fields[name]) and not read_only:
					raise common.FieldConfigChangedError(name)
		else:
			if read_only: raise RuntimeError('Search index does not exist, cannot create in read_only mode')
			# or b) create a schema containing only the required fields `'hash'` and `'comments'`.
			schema = fields.Schema()
			schema.add('hash', self.configured_fields['hash'])
			schema.add('comments', self.configured_fields['comments'])

			self.index = index.create_in(base_path, schema)

		self._open_writer = None

		# Finally, we create the alias map for the parser plugin above.
		self.field_alias_map = {}

		for field, value in self.db.fields.items():
			for alias in value['aliases']:
				self.field_alias_map[alias] = field

	def _writer(self):
		if self.read_only: raise common.DatabaseReadOnlyError()

		if not self._open_writer: 
			# This is a kind of terrible hack to give us roughly-atomic checkpoints.
			self._open_writer = writing.BufferedWriter(self.index, limit = sys.maxsize, period = None)

		return self._open_writer

	def _searcher(self):
		if self._open_writer: 
			return self._open_writer.searcher()
		else:
			return self.index.searcher()

	def _schema(self):
		if self._open_writer: 
			return self._open_writer.schema
		else:
			return self.index.schema

	# Flushes all pending index changes.
	def commit(self):
		if self._open_writer: self._open_writer.commit()

	# Adds a new file to the database.
	def add(self, hash):
		writer = self._writer()
		# We use update_document, rather than add_document, so that this function can be mostly
		# idempotent.
		writer.update_document(hash = hash)

	# Returns all files in the database.
	def all(self):
		with self._searcher() as searcher:
			for _, metadata in searcher.iter_docs():
				yield metadata

	# Gets a `dict` of all the metadata for the given file.
	def get(self, hash):
		with self._searcher() as searcher:
			return searcher.document(hash = hash)

	# Find whether the given document exists.
	def exists(self, hash):
		with self._searcher() as searcher:
			return bool(searcher.document_number(hash = hash))

	# Find all hashes starting with the given prefix.
	def find_hashes(self, prefix):
		with self._searcher() as searcher:
			for docnum in searcher.docs_for_query(query.Prefix('hash', prefix)):
				yield searcher.stored_fields(docnum)['hash']

	# Internal utility method to parse the given search query.
	def _parse_query(self, query):
		# We default to searching the comments field if no explicit field is given.
		parser = qparser.QueryParser('comments', self._schema())
		# Add support for using >, <, <=, etc. in numeric/timestamp fields.
		parser.add_plugin(qparser.GtLtPlugin())
		# Parse * as a wildcard.
		parser.add_plugin(qparser.WildcardPlugin())
		# Reconfigure the named field plugin to support field names containing hyphens and periods.
		parser.replace_plugin(qparser.FieldsPlugin(expr=r"(?P<text>[\w.-]+|[*]):", remove_unknown = False))
		# And finally add our field alias plugin.
		parser.add_plugin(_FieldAliasPlugin(self.field_alias_map))

		return parser.parse(query)

	# Runs a search and returns the result.
	def search(self, query_text, limit):
		q = self._parse_query(query_text)

		# As this `with` holds the search index open, this iterator should be read to completion.
		with self._searcher() as searcher:
			results = searcher.search(q, limit = limit)

			for result in results:
				yield dict(result)

	# Deletes all the metadata for the given file.
	def delete(self, f):
		writer = self._writer()
		writer.delete_by_term('hash', f.hash)

	# Saves the metadata for the given `File` to the database.
	def save(self, f):
		writer = self._writer()

		# We only add new fields when they are actually used, so they can be reconfigured up until
		# that point.
		for field in f.metadata:
			if field not in self._schema().names():
				if field not in self.configured_fields:
					raise common.FieldDoesNotExistError(field)

				writer.add_field(field, self.configured_fields[field])

		writer.update_document(**f.metadata)

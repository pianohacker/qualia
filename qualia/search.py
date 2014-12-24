from . import config, common

import copy
from whoosh import analysis, fields, index, qparser, query

def _create_field_type(field_config):
	return dict(
		datetime = fields.DATETIME(stored = True),
		exact_text = fields.ID(stored = True),
		id = fields.ID(unique = True, stored = True),
		keyword = fields.KEYWORD(stored = True),
		number = fields.NUMERIC(stored = True),
		text = fields.TEXT(analyzer = analysis.StemmingAnalyzer(), stored = True),
	)[field_config['type'].replace('-', '_')]

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

class SearchDatabase:
	def __init__(self, db, base_path):
		self.db = db
		self.configured_fields = {field: _create_field_type(value) for field, value in self.db.fields.items()}

		if index.exists_in(base_path):
			self.index = index.open_dir(base_path)

			for name, field in self.index.schema.items():
				if name not in self.configured_fields or field != self.configured_fields[name]:
					raise common.FieldConfigChangedError(name)
		else:
			schema = fields.Schema()
			for name, field in self.configured_fields.items():
				schema.add(name, field)

			self.index = index.create_in(base_path, schema)

		self.field_alias_map = {}

	def add(self, hash):
		writer = self.index.writer()
		# We use update_document, rather than add_document, so this function can be mostly
		# idempotent
		writer.update_document(hash = hash)
		writer.commit()

	def get(self, hash):
		q = query.Term('hash', hash)

		with self.index.searcher() as searcher:
			results = searcher.search(q, limit = 1)
			result = dict(results[0]) if len(results) == 1 else {}

		return result

	def parse_query(self, query):
		parser = qparser.QueryParser('comments', self.index.schema)
		parser.add_plugin(qparser.GtLtPlugin())
		parser.add_plugin(qparser.WildcardPlugin())
		parser.replace_plugin(qparser.FieldsPlugin(expr=r"(?P<text>[\w-]+|[*]):", remove_unknown = False))
		parser.add_plugin(_FieldAliasPlugin(self.field_alias_map))
		print(parser.process(query))

		return parser.parse(query)

	def search(self, query_text, limit):
		q = self.parse_query(query_text)

		with self.index.searcher() as searcher:
			results = searcher.search(q, limit = limit)

			for result in results:
				yield dict(result)

	def delete(self, f):
		writer = self.index.writer()
		writer.delete_by_term('hash', hash)
		writer.commit()

	def save(self, f):
		writer = self.index.writer()

		for field in f.metadata:
			if field not in self.index.schema.names():
				if field not in self.configured_fields:
					raise common.FieldDoesNotExistError(field)

				writer.add_field(field, self.configured_fields[field])

		writer.update_document(**f.metadata)
		writer.commit()

from . import config, common

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

class SearchDatabase:
	def __init__(self, base_path):
		self.configured_fields = {field: _create_field_type(value) for field, value in config.conf['metadata'].items()}

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

	def add(self, hash):
		writer = self.index.writer()
		writer.add_document(hash = hash)
		writer.commit()

	def get(self, hash):
		q = query.Term('hash', hash)

		with self.index.searcher() as searcher:
			results = searcher.search(q, limit = 1)
			result = dict(results[0]) if len(results) == 1 else {}

		return result

	def parse_query(self, query):
		parser = qparser.QueryParser('comments', self.index.schema)
		parser.add_plugin(qparser.WildcardPlugin())
		parser.replace_plugin(qparser.FieldsPlugin(expr=r"(?P<text>[\w-]+|[*]):"))

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

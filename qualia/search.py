from . import config

from whoosh import analysis, fields, index, qparser, query

class KeyDoesNotExistError(Exception):
	pass

class FieldChangedError(Exception):
	pass

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
		self.configured_fields = {key: _create_field_type(value) for key, value in config.conf['metadata'].items()}

		if index.exists_in(base_path):
			self.index = index.open_dir(base_path)

			for name, field in self.index.schema.items():
				if name not in self.configured_fields or field != self.configured_fields[name]:
					raise FieldChangedError(name)
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

	def delete(self, f):
		writer = self.index.writer()
		writer.delete_by_term('hash', hash)
		writer.commit()

	def save(self, f):
		writer = self.index.writer()

		for key in f.metadata:
			if key not in self.index.schema.names():
				if key not in self.configured_fields:
					raise KeyDoesNotExistError(key)

				writer.add_field(key, self.configured_fields[key])

		writer.update_document(**f.metadata)
		writer.commit()

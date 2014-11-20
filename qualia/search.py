from whoosh import analysis, fields, index, qparser, query

class SearchDatabase:
	def __init__(self, base_path):
		schema = fields.Schema(
			hash = fields.ID(stored = True, unique = True),
			comments = fields.TEXT(analyzer = analysis.StemmingAnalyzer(), stored = True)
		)

		if index.exists_in(base_path):
			self.index = index.open_dir(base_path)
		else:
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

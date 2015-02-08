from qualia import config

def register(**kwargs):
	config.DB_STATE_BASE['fields']['magic.mime-type'] = config.DerivedDictItem(config.FIELD_ITEM_BASE,
		'type', config.FixedItem('exact-text'),
		'aliases', ['mime', 'dc.format'],
	)

magic_db = None

def auto_add_magic(f, original_filename):
	global magic_db

	if magic_db is None:
		import magic

		magic_db = magic.open(magic.SYMLINK | magic.COMPRESS | magic.MIME_TYPE)
		magic_db.load()

	f.set_metadata('magic.mime-type', magic_db.file(original_filename), 'auto')

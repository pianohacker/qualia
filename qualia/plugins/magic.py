import magic

magic_db = magic.open(magic.SYMLINK | magic.COMPRESS | magic.MIME_TYPE)
magic_db.load()

def auto_add_magic(f, original_filename):
	f.set_metadata('magic-mime-type', magic_db.file(original_filename), 'auto')

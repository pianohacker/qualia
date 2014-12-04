##Imports
from . import common, config

import datetime
import os
from os import path
import parsedatetime
import stat
import time

def _parse_datetime(field_conf, text_value):
	cal = parsedatetime.Calendar()
	result = cal.parse(text_value)

	if not result:
		raise common.InvalidFieldValue(field, text_value)
		return

	return datetime.datetime.fromtimestamp(time.mktime(result[0]))

def _parse_exact_text(field_conf, text_value):
	return text_value

def _parse_number(field_conf, text_value):
	try:
		return float(text_value)
	except ValueError:
		raise common.InvalidFieldValue(field, text_value)

def _parse_text(field_conf, text_value):
	return text_value.strip()

_parse_keyword = _parse_text

def parse_metadata(field, text_value):
	field_conf = config.conf['metadata'][field]

	return globals().get('_parse_' + field_conf['type'].replace('-', '_'), _parse_exact_text)(field_conf, text_value)

def parse_editable_metadata(f, editable):
	pass

def _format_exact_text(field_conf, value):
	return str(value)

def format_metadata(field, value):
	field_conf = config.conf['metadata'][field]

	return globals().get('_format_' + field_conf['type'].replace('-', '_'), _format_exact_text)(field_conf, value)

def format_editable_metadata(f):
	result = []
	result.append('# qualia: editing metadata for file {}'.format(f.short_hash))
	result.append('#')
	result.append('# read-only fields:'.format(f.short_hash))

	read_only_fields = []
	editable_fields = []

	for field, value in sorted(f.metadata.items()):
		field_conf = config.conf['metadata'][field]

		text = '{}: {}'.format(field, format_metadata(field, value))

		if field_conf['read-only']:
			read_only_fields.append(text)
		else:
			editable_fields.append(text)

	result.extend(('#     ' + line) for line in read_only_fields)

	result.append('')

	result.extend(editable_fields)

	return '\n'.join(result)

def _auto_add_fs(f, original_filename):
	f.set_metadata('original-filename', path.abspath(original_filename), 'auto')

	s = os.stat(original_filename)

	f.set_metadata('modified-at', datetime.datetime.fromtimestamp(s.st_mtime), 'auto')

try:
	import magic
	magic_db = magic.open(magic.SYMLINK | magic.COMPRESS | magic.MIME_TYPE)
	magic_db.load()
except ImportError:
	magic_db = None

def _auto_add_fs(f, original_filename):
	f.set_metadata('original-filename', path.abspath(original_filename), 'auto')

	s = os.stat(original_filename)

	f.set_metadata('modified-at', datetime.datetime.fromtimestamp(s.st_mtime), 'auto')

def _auto_add_magic(f, original_filename):
	if magic_db is None: return
	f.set_metadata('mime-type', magic_db.file(original_filename), 'auto')

def auto_add_metadata(f, original_filename):
	f.set_metadata('imported-at', datetime.datetime.now(), 'auto')
	_auto_add_fs(f, original_filename)
	_auto_add_magic(f, original_filename)

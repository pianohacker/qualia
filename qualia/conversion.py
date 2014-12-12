# This file contains a number of utility functions for converting metadata to/from qualia's internal
# formats, text entered by the user or filesystem/embedded metadata.
#
##Imports
from . import common, config

import datetime
import os
from os import path
import parsedatetime
import re
import stat
import textwrap
import time
import yaml

## Parsing
# The functions below all are used to parse metadata entered by the user. `parse_metadata` is the
# entry point, and takes both the name and value of the field so it can look up the correct parser
# for the field's format.
#
# This parser uses parsedatetime, and can understand a number of date formats including
# (conveniently) the default string representation of datetime objects, English representations like
# 'tomorrow at ten', etc.
def _parse_datetime(field, field_conf, text_value):
	# First, try to parse the exact format we emit, as `parsedatetime` does not correctly handle it.
	exact_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.(\d{6})', text_value)
	if exact_match:
		try:
			base_dt = datetime.datetime.strptime(exact_match.group(1), '%Y-%m-%d %H:%M:%S')
		except ValueError:
			raise common.InvalidFieldValue(field, text_value)

		return base_dt  + datetime.timedelta(microseconds = int(exact_match.group(2)))

	# Then, try to parse a human date/time.
	cal = parsedatetime.Calendar()
	result = cal.parse(text_value)

	if not result:
		raise common.InvalidFieldValue(field, text_value)

	return datetime.datetime.fromtimestamp(time.mktime(result[0]))

# Besides parsing `exact-text` fields, this is also the fallback for any field type without a
# defined parser.
def _parse_exact_text(field, field_conf, text_value):
	return text_value.strip()

def _parse_number(field, field_conf, text_value):
	try:
		return float(text_value)
	except ValueError:
		raise common.InvalidFieldValue(field, text_value)

def parse_metadata(f, field, text_value):
	field_conf = f.db.state['metadata'][field]

	return globals().get('_parse_' + field_conf['type'].replace('-', '_'), _parse_exact_text)(field, field_conf, text_value)

# This function is used for `qualia edit`, and takes any changes made to the textual version of the
# metadata and applies them to the given file.
def parse_editable_metadata(f, editable):
	modifications = []

	for raw_line in editable.split('\n'):
		line = ''
		chars = iter(raw_line)
		try:
			while True:
				c = next(chars)
				if c == '\\':
					c = next(chars)
				elif c == '#':
					break

				line += c
		except StopIteration: pass

		if re.match(r'^\s*$', line): continue

		field, text_value = line.split(':', 1)
		value = parse_metadata(field, text_value[1:])

		if value != f.metadata[field]:
			modifications.append((field, value))
			f.set_metadata(field, value)

	return modifications

## Formatting
# These functions follow the same format as the implementations for `parse_metadata`, though there
# are no specialized formatters yet. The only constraint on these formatters is that the matching
# parser for their field type should be able to parse their output.
def _format_exact_text(field_conf, value):
	return str(value)

def format_metadata(f, field, value):
	field_conf = f.db.state['metadata'][field]

	return globals().get('_format_' + field_conf['type'].replace('-', '_'), _format_exact_text)(field_conf, value)

def format_editable_metadata(f):
	result = []
	result.append('# qualia: editing metadata for file {}'.format(f.short_hash))
	result.append('#')
	result.append('# read-only fields:'.format(f.short_hash))

	read_only_fields = []
	editable_fields = []

	for field, value in sorted(f.metadata.items()):
		field_conf = f.db.state['metadata'][field]

		text = '{}: {}'.format(field, re.sub(r'(\\|#)', r'\\\1', format_metadata(field, value)))

		if field_conf['read-only']:
			read_only_fields.append(text)
		else:
			editable_fields.append(text)

	result.extend(('#     ' + line) for line in read_only_fields)

	result.append('')

	result.extend(editable_fields)

	return '\n'.join(result)

def format_yaml_metadata(f):
	return f.hash + ':\n' + textwrap.indent(
		yaml.dump(
			{key: value for key, value in f.metadata.items() if key != 'hash'},
			default_flow_style = False
		),
		'  '
	)

try:
	import magic
	magic_db = magic.open(magic.SYMLINK | magic.COMPRESS | magic.MIME_TYPE)
	magic_db.load()
except ImportError:
	magic_db = None

def _auto_add_fs(f, original_filename):
	f.set_metadata('filename', path.abspath(original_filename), 'auto')

	s = os.stat(original_filename)

	f.set_metadata('file-modified-at', datetime.datetime.fromtimestamp(s.st_mtime), 'auto')

def _auto_add_magic(f, original_filename):
	if magic_db is None: return
	f.set_metadata('mime-type', magic_db.file(original_filename), 'auto')

def auto_add_metadata(f, original_filename):
	f.set_metadata('imported-at', datetime.datetime.now(), 'auto')
	_auto_add_fs(f, original_filename)
	_auto_add_magic(f, original_filename)

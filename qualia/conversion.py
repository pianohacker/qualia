# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
# 
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

##Imports
from . import common, config

import datetime
import io
import os
from os import path
import parsedatetime
import pickle
import pkg_resources
import re
import stat
import textwrap
import time
import yaml
import zipfile

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

def _parse_keyword(field, field_conf, text_value):
	return ' '.join(text_value.strip().split())

def _parse_number(field, field_conf, text_value):
	try:
		return float(text_value)
	except ValueError:
		raise common.InvalidFieldValue(field, text_value)

def parse_metadata(f, field, text_value):
	field_conf = f.db.fields[field]

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
		value = parse_metadata(f, field, text_value[1:])

		if value != f.metadata.get(field):
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
	field_conf = f.db.fields[field]

	return globals().get('_format_' + field_conf['type'].replace('-', '_'), _format_exact_text)(field_conf, value)

def format_editable_metadata(f):
	result = []
	result.append('# qualia: editing metadata for file {}'.format(f.short_hash))
	result.append('#')
	result.append('# read-only fields:'.format(f.short_hash))

	read_only_fields = []
	editable_fields = []

	for field, value in sorted(f.metadata.items()):
		field_conf = f.db.fields[field]

		text = '{}: {}'.format(field, re.sub(r'(\\|#)', r'\\\1', format_metadata(f, field, value)))

		if field_conf['read-only']:
			read_only_fields.append(text)
		else:
			editable_fields.append(text)

	result.extend(('#     ' + line) for line in read_only_fields)

	result.append('')

	result.extend(editable_fields)

	return '\n'.join(result)

# Formats a checkpoint into YAML.
def format_yaml_checkpoint(checkpoint):
	return '-\n' + textwrap.indent(
		yaml.safe_dump(
			checkpoint,
			default_flow_style = False
		),
		'  '
	)

# Formats metadata into true YAML.
def format_yaml_metadata(f):
	return f.hash + ':\n' + textwrap.indent(
		# Note; we mainly use `safe_dump` so that we know a later `safe_load` will work. In theory,
		# all types we feed this function should be safe.
		yaml.safe_dump(
			{key: value for key, value in f.metadata.items() if key != 'hash'},
			default_flow_style = False
		),
		'  '
	)

## Import/export
# Qualia can import and export metadata/file contents in specially arranged ZIPs.
#
# These ZIPs have the following layout:
#
# * /
#     * qualia_export.yaml - State file; marks this as a qualia export and holds version information
#     * metadata.yaml - Contains metadata for all exported files
#     * files/ - Unless `metadata_only` set in `qualia_export.yaml`
#         * ... - Contents of files, stored under their full hash

EXPORT_VERSION = 1

def export(db, output_file, hashes, *, metadata_only = False):
	# The default filename is just a timestamp with our special `.qualia` extension.
	output_file = output_file or open(datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S.qualia'), 'wb')

	# Note: we do this early and with a list so we catch all missing/ambiguous hashes early.
	files = db.all() if hashes is None else [db.get(hash) for hash in hashes]

	with zipfile.ZipFile(file = output_file, mode = 'w', compression = zipfile.ZIP_DEFLATED, allowZip64 = True) as out:
		# We make sure to use the same timestamp for all operations, for consistency.
		# This trick with slicing localtime is from the `zipfile` module.
		timestamp = time.localtime()[:6]
		info = zipfile.ZipInfo('qualia_export.yaml', timestamp)
		state = yaml.safe_dump({
			'version': EXPORT_VERSION,
			'metadata_only': metadata_only,
			'timestamp': timestamp,
		}).encode('utf-8')
		info.compress_type = zipfile.ZIP_DEFLATED
		out.writestr(info, state)

		if not metadata_only:
			out.writestr('files/', '')

		# This seems to be the easiest way to output encoded data to a `BytesIO`.
		metadata_raw_out = io.BytesIO() 
		metadata_out = io.TextIOWrapper(metadata_raw_out, encoding = 'utf-8')

		for f in files:
			metadata_out.write(format_yaml_metadata(f))

			if not metadata_only:
				out.write(db.get_filename(f), 'files/' + f.hash)

		metadata_out.flush()
		info = zipfile.ZipInfo('metadata.yaml', timestamp)
		info.compress_type = zipfile.ZIP_DEFLATED
		out.writestr(info, metadata_raw_out.getvalue())

# This import routine is missing a lot of error handling:
#
#   * No checks to see if the import file is actually a tarball.
#   * No check to see if `qualia_export.yaml` is actually YAML.
#
def import_(db, input_file, *, renames = {}, trust_hash = False):
	metadata = {}

	with zipfile.ZipFile(file = input_file, mode = 'r') as zipf:
		export_info = yaml.safe_load(zipf.open('qualia_export.yaml'))
		assert(export_info['version'] == 1)

		metadata = yaml.safe_load(zipf.open('metadata.yaml'))

		for info in zipf.infolist():
			if info.filename in ('qualia_export.yaml', 'metadata.yaml'):
				continue
			elif info.filename.startswith('files/') and info.filename[-1] != '/':
				try:
					f = db.add_file(zipf.open(info))
					for key, value in metadata.get(f.hash, {}).items():
						f.set_metadata(renames.get(key, key), value)
					db.save(f)
					print('imported {}'.format(f.short_hash))
				except common.FileExistsError: print('{}: identical file in database, not added'.format(info.filename))

	db.commit()

## Automatic metadata
# A good portion of the metadata for a given file is automatically generated from filesystem
# attributes, media metadata, etc. Some of this is built in, and some of it comes from plugins.
importers = None

def _load_importers():
	global importers
	importers = []

	for ep in pkg_resources.iter_entry_points(group = 'qualia.auto_metadata_importers'):
		importers.append(ep.load())

def auto_add_metadata(f, original_filename):
	if importers is None:
		_load_importers()

	f.set_metadata('imported-at', datetime.datetime.now(), 'auto')

	f.set_metadata('filename', path.abspath(original_filename), 'auto')

	s = os.stat(original_filename)

	f.set_metadata('file-modified-at', datetime.datetime.fromtimestamp(s.st_mtime), 'auto')

	for importer in importers: importer(f, original_filename)

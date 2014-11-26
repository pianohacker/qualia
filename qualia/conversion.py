from . import common, config

import datetime
import parsedatetime
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

_parse_id = _parse_exact_text

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

def show_metadata(field, value):
	pass

def _auto_load_fs(f, original_filename):

def auto_load_metadata(f, original_filename):
	_auto_load_fs(f, original_filename)

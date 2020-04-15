# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from . import query

import datetime
import parsy as p

## Supporting parsers
# Like `parsy.eof`, but with a different, less confusing description.
@p.Parser
def _end_of_query_value(stream, index):
	if index >= len(stream):
		return p.Result.success(index, None)
	else:
		print(repr(stream[index:]))
		return p.Result.failure(index, 'end of query value')

_query_string_value = (p.string('"') >> p.regex(r'[^"]+') << p.string('"') << p.regex('[^,]*')).desc('quoted phrase') | p.regex('[^,]+').map(lambda x: x.rstrip(' ')).desc('unquoted phrase')
_optional_whitespace = p.regex('\s*')

@p.Parser
def _query_value(stream, index):
	@p.generate
	def query_date_value():
		year = yield (p.regex(r'\d{4}') << p.string('-')).map(int)
		month = yield (p.regex(r'\d{2}') << p.string('-')).map(int)
		day = yield p.regex(r'\d{2}').map(int)

		try:
			return datetime.date(year, month, day)
		except ValueError as e:
			return p.fail(str(e))

	query_number_value = p.regex('\d+(?:\.\d*)?|\.\d+').map(float).desc('number')

	return ((query_date_value | query_number_value | _query_string_value) << _optional_whitespace << _end_of_query_value)(stream, index)

## Parsing
def parse_query(q_text):
	whitespace = p.regex('\s+')
	term_sep = p.regex('\s*,\s*')

	property_name = p.regex('[A-Za-z0-9_-]+').desc('property name')

	# This construction parses the query value as a basic string first, to find out the extent of
	# the query value, then reparses only the part that was matched. This allows the underlying
	# parsers to more strictly match values (which disambiguates numbers and dates better).
	def query_value_part(terminators = r',|$'):
		@p.Parser
		def query_value_part_impl(stream, index):
			string_result = p.regex(rf'("[^"]+".*?|.+?)(?={terminators})')(stream, index)

			if not string_result.status:
				raise p.ParseError(string_result.expected, stream, string_result.furthest)

			return _query_value(stream[:string_result.index], index)

		return query_value_part_impl

	eq_query = p.seq(
		p.regex('\s*=\s*').map(lambda _: query.EqualityQuery).desc('equality match (=)'),
		query_value_part(),
	)
	phrase_query = p.seq(
		p.regex('\s*:\s*').map(lambda _: query.PhraseQuery).desc('phrase match (:)'),
		_query_string_value,
	)
	_and = f'\s+and\s+'
	between_query = p.seq(
		p.regex('\s*between\s*').map(lambda _: query.BetweenQuery).desc('between match'),
		query_value_part(_and),
		p.regex(_and).desc('and') >> query_value_part(),
	)

	@p.generate
	def prop_query():
		yield _optional_whitespace
		prop_name = yield property_name
		node_type, *match_vals = yield (eq_query | phrase_query | between_query)
		yield _optional_whitespace
		return node_type(prop_name, *match_vals)

	terms = prop_query.sep_by(term_sep)

	q_terms = terms.parse(q_text)
	return query.AndQueries(*q_terms) if q_terms else query.Empty()

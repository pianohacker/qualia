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
import re

## Supporting parsers
# Like `parsy.eof`, but with a different, less confusing description.
@p.Parser
def _end_of_query_value(stream, index):
	if index >= len(stream):
		return p.Result.success(index, None)
	else:
		print(repr(stream[index:]))
		return p.Result.failure(index, 'end of query value')

# Like `parsy.regex`, but returns the groups rather than the main match. If there's only one group,
# will return its contents; otherwise, will return all groups in a tuple.
def _regex_groups(pattern, flags = 0):
	compiled_pattern = re.compile(pattern, flags)

	@p.Parser
	def regex_groups_parser(stream, index):
		match = compiled_pattern.match(stream, index)

		if match:
			return p.Result.success(match.end(), match.groups()[0] if compiled_pattern.groups == 1 else match.groups())
		else:
			return p.Result.failure(index, compiled_pattern.pattern)

	return regex_groups_parser

_query_number_value = p.regex('\d+(?:\.\d*)?|\.\d+').map(float).desc('number')
_query_string_value = (
	_regex_groups(r'"([^"]+)"[^,]*').desc('quoted phrase') |
	p.regex('[^,]+').map(lambda x: x.rstrip(' ')).desc('unquoted phrase')
)
@p.generate
def _query_date_value():
	year = yield (p.regex(r'\d{4}') << p.string('-')).map(int)
	month = yield (p.regex(r'\d{2}') << p.string('-')).map(int)
	day = yield p.regex(r'\d{2}').map(int)

	try:
		return datetime.date(year, month, day)
	except ValueError as e:
		return p.fail(str(e))

_optional_whitespace = p.regex('\s*')

def _lexeme(s):
	return p.regex(rf'\s*{s}\s').desc(s)

## Parsing
def parse_query(q_text):
	whitespace = p.regex('\s+')
	term_sep = _lexeme(',')

	property_name = p.regex('[A-Za-z0-9_-]+').desc('property name')

	# This construction parses the query value as a basic string first, to find out the extent of
	# the query value, then reparses only the part that was matched. This allows the underlying
	# parsers to more strictly match values (which disambiguates numbers and dates better).
	def query_value_part(*, delimiter = r',|$', parser = _query_string_value):
		@p.Parser
		def query_value_part_impl(stream, index):
			string_result = p.regex(rf'("[^"]+".*?|.+?)(?={delimiter})')(stream, index)

			if not string_result.status:
				raise p.ParseError(string_result.expected, stream, string_result.furthest)

			return parser(stream[:string_result.index], index)

		return query_value_part_impl

	eq_query = p.seq(
		_lexeme('exactly').map(lambda _: query.EqualityQuery).desc('exactly query'),
		query_value_part(),
	)
	_and = f'\s+and\s+'
	between_dates_query = p.seq(
		_lexeme('between\s+dates').map(lambda _: query.BetweenDatesQuery).desc('between dates query'),
		query_value_part(delimiter = _and, parser = _query_date_value),
		p.regex(_and).desc('and') >> query_value_part(parser = _query_date_value),
	)
	between_numbers_query = p.seq(
		_lexeme('between').map(lambda _: query.BetweenNumbersQuery).desc('between (numbers) query'),
		query_value_part(delimiter = _and, parser = _query_number_value),
		p.regex(_and).desc('and') >> query_value_part(),
	)

	@p.generate
	def phrase_query():
		phrase = yield _query_string_value

		return query.PhraseQuery, phrase

	@p.generate
	def prop_query():
		yield _optional_whitespace
		prop_name = yield property_name
		yield p.regex('\s*:\s*').desc(':')
		node_type, *match_vals = yield (eq_query | between_dates_query | between_numbers_query | phrase_query)
		yield _optional_whitespace
		return node_type(prop_name, *match_vals)

	terms = prop_query.sep_by(term_sep)

	q_terms = terms.parse(q_text)
	return query.AndQueries(*q_terms) if q_terms else query.Empty()

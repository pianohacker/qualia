# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
#
# Qualia is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Qualia is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Qualia. If not, see <http://www.gnu.org/licenses/>.

import abc
import typing

PropertyValue = typing.Union[float, str]

# These nodes form the basis of a tree, which can be created by parsers and turned into SQL queries.

## Base types
class Node(abc.ABC):
	def __repr__(self):
		member_reprs = ", ".join(f"{k} = {v!r}" for (k,v) in vars(self).items() if not k.startswith('_'))
		return f'{self.__class__.__name__}({member_reprs})'

	def visit(self, handlers: dict):
		for t, handler in handlers.items():
			if isinstance(self, t):
				return handler(self)

		raise KeyError(f'No handler for {self!r}')

class CompoundNode(Node, abc.ABC):
	children: typing.Tuple[Node]

	def __init__(self, *children):
		self.children = children

	def visit_children(self, handlers):
		return [child.visit(handlers) for child in self.children]

## Terminal queries
class EqualityQuery(Node):
	property: str
	value: PropertyValue

	def __init__(self, property, value):
		self.property = property
		self.value = value

class PhraseQuery(Node):
	property: str
	phrase: str

	def __init__(self, property, phrase):
		self.property = property
		self.phrase = phrase

class BetweenQuery(Node):
	property: str
	min: float
	max: float

	def __init__(self, property, min, max):
		self.property = property
		self.min = min
		self.max = max

class Empty(Node):
	pass

## Compound matchers
class AndQueries(CompoundNode):
	pass

## Parsing
def parse(q_text):
	import parsy as p

	whitespace = p.regex('\s*')

	property_name = p.regex('[A-Za-z0-9_-]+').desc('property name')
	query_number_value = p.regex('\d+(?:\.\d*)?|\.\d+').map(float).desc('number')
	query_string_value = (p.string('"') >> p.regex(r'[^"]+') << p.string('"')).desc('quoted phrase') | p.regex('[^,]+').map(lambda x: x.rstrip(' ')).desc('unquoted phrase')
	query_value = query_number_value | query_string_value

	eq_query = p.seq(
		p.regex('\s*=\s*').map(lambda _: EqualityQuery),
		query_value,
	).desc('equality match (=)')
	phrase_query = p.seq(
		p.regex('\s*:\s*').map(lambda _: PhraseQuery),
		query_string_value,
	).desc('phrase match (:)')
	between_query = p.seq(
		p.regex('\s*between\s*').map(lambda _: BetweenQuery),
		query_number_value,
		p.regex('\s*and\s*') >> query_number_value,
	).desc('between match')

	@p.generate
	def prop_query():
		yield whitespace
		prop_name = yield property_name
		node_type, *match_vals = yield (eq_query | phrase_query | between_query)
		yield whitespace
		return node_type(prop_name, *match_vals)

	terms = prop_query.sep_by(p.regex('\s*,\s*'))

	q_terms = terms.parse(q_text)
	return AndQueries(*q_terms) if q_terms else Empty()
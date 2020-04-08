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

## Terminal matchers
class EqualityMatch(Node):
	property: str
	value: PropertyValue

	def __init__(self, property, value):
		self.property = property
		self.value = value

class PhraseMatch(Node):
	property: str
	phrase: str

	def __init__(self, property, phrase):
		self.property = property
		self.phrase = phrase

class Empty(Node):
	pass

## Compound matchers
class AndMatchers(CompoundNode):
	pass

## Parsing
def parse(q_text):
	import parsy as p

	whitespace = p.regex('\s*')

	property_name = p.regex('[A-Za-z0-9_-]+').desc('property name')
	property_value = (p.string('"') >> p.regex(r'[^"]+') << p.string('"')).desc('quoted phrase') | p.regex('[^,]+').map(lambda x: x.rstrip(' ')).desc('unquoted phrase')

	eq_match = (p.seq(p.regex('\s*=\s*').map(lambda _: EqualityMatch), property_value)).desc('equality match (=)')
	phrase_match = (p.seq(p.regex('\s*:\s*').map(lambda _: PhraseMatch), property_value)).desc('phrase match (:)')

	@p.generate('matcher')
	def matcher():
		yield whitespace
		prop_name = yield property_name
		node_type, match_val = yield (eq_match | phrase_match)
		yield whitespace
		return node_type(prop_name, match_val)

	terms = matcher.sep_by(p.regex('\s*,\s*'), min=1).combine(AndMatchers)

	empty = p.eof.map(lambda _: Empty())

	query = terms | empty

	return query.parse(q_text)

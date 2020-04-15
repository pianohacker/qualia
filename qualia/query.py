# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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

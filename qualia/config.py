# Copyright (c) 2015 Jesse Weaver.
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

## Imports
from .lazy_import import lazy_import

lazy_import(globals(), """
	import copy
	import os
	from os import path
	import yaml
""")

## Utility functions
# This returns the first of its arguments that are not `None` (if any).
def first_set(*args):
	for arg in args:
		if arg is not None: return arg

	return None

# Returns the default path to the config file (respecting XDG).
def get_default_path():
	return path.join(os.environ.get('XDG_CONFIG_HOME', path.expanduser('~/.config')), 'qualia.yaml')

## Exceptions
# This exception is thrown when a read-only config variable is changed or a variable is set to an
# invalid value.
class ConstrainedError(Exception):
	def __init__(self, path, message):
		self.path = path
		self.message = message

## Config hierarchy
# Each level in the hierarchy is represented by some kind of `Item`. This base type can take care of
# a basic value with a set type and default value, and has three key methods that can be overridden
# for more complex items.
class Item:
	# Any values set for this item will be checked to make sure they inherit from `type`. As with
	# `isinstance`, `type` can be a tuple of types. It can also be a `set` of possible values, in
	# which case the defined value must be in the set.
	#
	# `default` will be used if the value is not set in the user's config. Note that it is not
	# checked against `type`.
	def __init__(self, type, default):
		self.type = type
		self.default = default

	# This method should return the difference between the given value and this item's default, or
	# `None`. This is used for saving configuration files back to disk, and ensures that only the
	# values that are different are saved.
	def diff(self, value):
		return value if value != self.default else None

	# This method should return the result of applying the given `value` to this item, possibly
	# given an already loaded config value `start`  which may be `None`.
	def merge(self, start, value):
		return first_set(value, start, self.default)

	# And finally, this method should check that the given value is valid for this item.
	#
	# The path argument should be passed along to any recursive calls, and indicates where in the
	# config hierarchy any errors occured.
	def verify(self, path, value):
		if value is None: return

		# The base implementation simply checks that the value is either:
		if isinstance(self.type, set):
			# a) one of the values given
			if value not in self.type:
				# This is the first example of a widespread problem within this module; unlike most
				# of the backend module, this module creates exceptions with embedded messages. This
				# could make future translation difficult.
				raise ConstrainedError(path, 'must be one of {}'.format(', '.join(repr(x) for x in self.type)))
		elif not isinstance(value, self.type):
			# or b) inherits from the given type
			raise ConstrainedError(path, 'must be a {}'.format(self.type.__name__))

# This converts the Perl-style (key, value, key, value) argument list passed to the `DictItem`
# classes into an actual hash. This is a bit unidiomatic, but means there isn't an awkward
# transformation between the config keys seen here and those in the config file.
def from_flat_hash(*args):
	return dict(zip(args[::2], args[1::2]))

# `DictItem`s represent mappings within the config hierarchy, and can contain default values for
# given names underneath it and for any missing name (under the key `_other`).
#
# Values provided for these items are merged in recursively, with each child item controlling how
# provided values are merged.
class DictItem(Item):
	def __init__(self, *args):
		super().__init__(dict, args[0] if isinstance(args[0], dict) else from_flat_hash(*args))

	# This magic method is given for convenience when merging part of a config hierarchy.
	def __getitem__(self, key):
		return self.default[key]

	def __setitem__(self, key, value):
		self.default[key] = value

	def diff(self, value):
		result = {}

		for key in value:
			if key in self.default:
				diff = self.default[key].diff(value[key])
			elif '_others' in self.default:
				diff = self.default['_others'].diff(value[key])
			else:
				diff = None

			if diff is not None: result[key] = diff

		return result or None

	def merge(self, start, value, *, known_only = False):
		start = start or {}
		result = dict(start)
		value = value or {}

		for key in self.default:
			if key == '_others': continue
			result[key] = self.default[key].merge(start.get(key), value.get(key))
		
		if not known_only:
			for key in set(value) - set(self.default):
				result[key] = self.default['_others'].merge(start.get(key), value[key])

		return result

	def verify(self, path, value):
		if value is None: return

		super().verify(path, value)

		for key in self.default:
			if key == '_others': continue
			self.default[key].verify(key if path is None else (path + '.' + key), value.get(key))

		extra_keys = set(value) - set(self.default)
		if not extra_keys: return

		if '_others' in self.default:
			for key in extra_keys:
				self.default['_others'].verify(key if path is None else (path + '.' + key), value[key])
		else:
			raise ConstrainedError(path, 'unexpected keys: {}'.format(', '.join(repr(x) for x in extra_keys)))

# This subclass of `DictItem` makes it easy to create a new `DictItem` based on an existing one but
# with additional or changed keys.
#
# As a shortcut, if one provides something besides an `Item` subclass for a key, it is assumed that
# one only wishes to change the default value for that key.
class DerivedDictItem(DictItem):
	def __init__(self, base, *args):
		new_default = dict(base.default)

		for key, item in from_flat_hash(*args).items():
			if isinstance(item, Item):
				new_default[key] = item
			else:
				new_item = copy.copy(base.default[key])
				new_item.default = item

				new_default[key] = new_item

		super().__init__(new_default)

# This subclass is used to create an item with a fixed type and value.
class FixedItem(Item):
	def __init__(self, value):
		super().__init__(type(value), value)

	def diff(self, value):
		return None

	def merge(self, start, value):
		return self.default

	def verify(self, path, value):
		if value != None and value != self.default:
			raise ConstrainedError(path, 'cannot be changed')

# This string-specific subclass is used for paths, and will expand any tildes in the provided value.
class PathItem(Item):
	def __init__(self, value):
		super().__init__(str, value)

	def merge(self, start, value):
		result = first_set(value, start, self.default)

		# However, it can still contain `None`.
		return result if result is None else path.expanduser(result)

# Like `DictItem`, this subclass contains other `Item`s, but this time only takes a single `Item` as
# an argument, which all child values will be compared against.
class ListItem(Item):
	def __init__(self, child_item, value):
		super().__init__(list, value)

		self.child_item = child_item

	def verify(self, path, value):
		if value is None: return

		super().verify(path, value)

		for i, x in enumerate(value):
			key = '[{}]'.format(i)
			self.child_item.verify(key if path is None else (path + key), x)

# This item will not attempt to do any validity checking of any provided values. It is currently
# used for the metadata block in the global config, which is checked and merged against the database
# state.
class NoVerifyItem(Item):
	def __init__(self, value):
		super().__init__(None, value)

	def verify(self, path, value):
		pass

## Default config hierarchies
# This is the base used for all of the `DerivedDictItem`s defined for the default metadata fields.
FIELD_ITEM_BASE = DictItem(
	'type', Item(set(['exact-text', 'text', 'id', 'number', 'keyword', 'datetime']), 'text'),
	'aliases', ListItem(Item(str, None), []),
	'read-only', Item(bool, False),
	'shown', Item(bool, True),
)

# Each of the following bases represents the layout of their respective config files. For instance,
# a valid config file for `CONF_BASE` would be:
#
#> database-path: ~/q
#
# which would be merged to yield a final result of `{'database-path': '/home/user/q', 'fields':
# {}}`.
#
# This particular base is for the user's global config file.
CONF_BASE = DictItem(
	'database-path', PathItem(None),
	'fields', NoVerifyItem({}),
)

# This base, on the other hand, is for the database state file, which is not intended to be edited
# by the user.
DB_STATE_BASE = DictItem(
	'version', Item(int, None),
	# There is a complicated song and dance done in `qualia.database` to make sure that any
	# modifications the user has done to the metadata fields in their global config file are applied
	# to the fields configuration but not saved back to the state file.
	'fields', DictItem(
		'hash', DerivedDictItem(FIELD_ITEM_BASE,
			'type', FixedItem('id'),
			'read-only', FixedItem(True),
			'shown', Item(bool, False),
		),
		'comments', DerivedDictItem(FIELD_ITEM_BASE,
			'type', FixedItem('text'),
		),
		'file-modified-at', DerivedDictItem(FIELD_ITEM_BASE,
			'type', FixedItem('datetime'),
		),
		'filename', DerivedDictItem(FIELD_ITEM_BASE,
			'type', FixedItem('exact-text'),
		),
		'imported-at', DerivedDictItem(FIELD_ITEM_BASE,
			'type', FixedItem('datetime'),
		),
		'tags', DerivedDictItem(FIELD_ITEM_BASE,
			'type', FixedItem('keyword'),
		),
		'_others', FIELD_ITEM_BASE,
	),
)

conf = {}

## Functions
# This is the base config loader. It can take a value and merge it on top of the base (and
# optionally a starting value.)
#
# If `known_only` is true, then the top level will ignore any keys that did not exist in the
# starting value.
def load_value(value, base, *, start = None, known_only = False):
	base.verify(None, value)
	return base.merge(start, value, known_only = known_only)

# Same as the above, but will try to load YAML from `filename`, using `None` if that fails.
def load(filename, base, *, start = None, known_only = False):
	try:
		user_config = yaml.load(open(filename, 'r', encoding = 'utf-8'))
	except FileNotFoundError:
		user_config = {}

	return load_value(user_config, base, start = start, known_only = known_only)

# Saves any parts of the given config that have changed back to filename as YAML. This should only
# be used for non-user-visible config files, as it will destroy their formatting and comments.
def save(filename, value, base):
	diff = base.diff(value)
	if diff: yaml.dump(diff, stream = open(filename, 'w', encoding = 'utf-8'), default_flow_style = False)

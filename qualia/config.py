import copy
import os
from os import path
import yaml

def first_set(*args):
	for arg in args:
		if arg is not None: return arg

	return None

def get_default_path():
	return path.join(os.environ.get('XDG_CONFIG_HOME', path.expanduser('~/.config')), 'qualia.yaml')

class ConstrainedError(Exception):
	def __init__(self, path, message):
		self.path = path
		self.message = message

class Item:
	def __init__(self, type, default):
		self.type = type
		self.default = default

	def diff(self, value):
		return value if value != self.default else None

	def merge(self, start, value):
		return first_set(value, start, self.default)
	
	def verify(self, path, value):
		if value is None: return

		if isinstance(self.type, set):
			if value not in self.type:
				raise ConstrainedError(path, 'must be one of {}'.format(', '.join(repr(x) for x in self.type)))
		elif not isinstance(value, self.type):
			raise ConstrainedError(path, 'must be a {}'.format(self.type.__name__))

class DictItem(Item):
	def __init__(self, **kwargs):
		super().__init__(dict, {key.replace('_', '-'): value for key, value in kwargs.items()})

	def __getitem__(self, key):
		return self.default[key]

	def diff(self, value):
		result = {}

		for key in value:
			if key in self.default:
				diff = self.default[key].diff(value[key])
			elif '-others' in self.default:
				diff = self.default['-others'].diff(value[key])
			else:
				diff = None

			if diff is not None: result[key] = diff

		return result or None

	def merge(self, start, value, *, known_only = False):
		start = start or {}
		result = dict(start)
		value = value or {}

		for key in self.default:
			if key == '-others': continue
			result[key] = self.default[key].merge(start.get(key), value.get(key))
		
		if not known_only:
			for key in set(value) - set(self.default):
				result[key] = self.default['-others'].merge(start.get(key), value[key])

		return result

	def verify(self, path, value):
		if value is None: return

		super().verify(path, value)

		for key in self.default:
			if key == '-others': continue
			self.default[key].verify(key if path is None else (path + '.' + key), value.get(key))

		extra_keys = set(value) - set(self.default)
		if not extra_keys: return

		if '-others' in self.default:
			for key in extra_keys:
				self.default['-others'].verify(key if path is None else (path + '.' + key), value[key])
		else:
			raise ConstrainedError(path, 'unexpected keys: {}'.format(', '.join(repr(x) for x in extra_keys)))

class DerivedDictItem(DictItem):
	def __init__(self, base, **kwargs):
		new_default = dict(base.default)

		for key, item in kwargs.items():
			if isinstance(item, Item):
				new_default[key] = item
			else:
				new_item = copy.copy(base.default[key])
				new_item.default = item

				new_default[key] = new_item

		super().__init__(**new_default)

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

class PathItem(Item):
	def __init__(self, value):
		super().__init__(str, value)

	def merge(self, start, value):
		result = first_set(value, start, self.default)

		return result if result is None else path.expanduser(result)

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

class NoVerifyItem(Item):
	def __init__(self, value):
		super().__init__(None, value)

	def verify(self, path, value):
		pass

_FIELD_ITEM = DictItem(
	type = Item(set(['exact-text', 'text', 'id', 'number', 'keyword', 'datetime']), 'text'),
	aliases = ListItem(Item(str, None), []),
	read_only = Item(bool, False),
	shown = Item(bool, True),
)

CONF_BASE = DictItem(
	database_path = PathItem(None),
	fields = NoVerifyItem({}),
)

DB_STATE_BASE = DictItem(
	version = Item(int, None),
	fields = DictItem(
		hash = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('id'),
			read_only = FixedItem(True),
			shown = Item(bool, False),
		),
		comments = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('text'),
		),
		file_modified_at = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('datetime'),
		),
		filename = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('exact-text'),
		),
		imported_at = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('datetime'),
		),
		image_height = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('number'),
			aliases = ['height'],
		),
		image_width = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('number'),
			aliases = ['width'],
		),
		magic_mime_type = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('exact-text'),
			aliases = ['mime'],
		),
		tags = DerivedDictItem(_FIELD_ITEM,
			type = FixedItem('keyword'),
		),
		_others = _FIELD_ITEM,
	),
)

conf = {}

def load_over(source, destination, base, *, known_only = False):
	base.verify(None, source)
	destination.update(base.merge(destination, source, known_only = known_only))

def load(filename, destination, base):
	try:
		user_config = yaml.load(open(filename, 'r', encoding = 'utf-8'))
	except FileNotFoundError:
		user_config = {}

	load_over(user_config, destination, base)

def save(filename, value, base):
	diff = base.diff(value)
	if diff: yaml.dump(diff, stream = open(filename, 'w', encoding = 'utf-8'), default_flow_style = False)

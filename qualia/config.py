import os
from os import path
import yaml

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
		return (self.default if start is None else start) if value is None else value
	
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

	def merge(self, start, value):
		start = start or {}
		result = dict(start)
		value = value or {}

		for key in self.default:
			if key == '-others': continue
			result[key] = self.default[key].merge(start.get(key), value.get(key))
		
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
		result = (self.default if start is None else start) if value is None else value

		return result if result is None else path.expanduser(result)

CONF_BASE = DictItem(
	database_path = PathItem(None)
)

DB_STATE_BASE = DictItem(
	version = Item(int, None),
	metadata = DictItem(
		hash = DictItem(
			type = FixedItem('id'),
			read_only = FixedItem(True),
			shown = Item(bool, False),
		),
		comments = DictItem(
			type = FixedItem('text'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		file_modified_at = DictItem(
			type = FixedItem('datetime'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		filename = DictItem(
			type = FixedItem('exact-text'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		imported_at = DictItem(
			type = FixedItem('datetime'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		image_height = DictItem(
			type = FixedItem('number'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		image_width = DictItem(
			type = FixedItem('number'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		magic_mime_type = DictItem(
			type = FixedItem('exact-text'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		tags = DictItem(
			type = FixedItem('keyword'),
			read_only = FixedItem(False),
			shown = Item(bool, True),
		),
		_others = DictItem(
			type = Item(set(['exact-text', 'text', 'id', 'number', 'keyword', 'datetime']), 'text'),
			read_only = Item(bool, False),
			shown = Item(bool, True),
		),
	),
)

conf = {}
db_state = {}

def load(filename, destination, base):
	try:
		user_config = yaml.load(open(filename, 'r', encoding = 'utf-8'))
	except FileNotFoundError:
		user_config = {}

	base.verify(None, user_config)
	destination.update(base.merge(destination, user_config))

def save(filename, value, base):
	diff = base.diff(value)
	if diff: yaml.dump(diff, stream = open(filename, 'w', encoding = 'utf-8'), default_flow_style = False)

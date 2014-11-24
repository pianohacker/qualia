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

	def merge(self, value):
		return self.default if value is None else value
	
	def verify(self, path, value):
		if value is None: return

		if isinstance(self.type, set):
			if value not in self.type:
				raise ConstrainedError(path, 'must be one of {}'.format(', '.join(repr(x) for x in self.type)))
		elif not isinstance(value, self.type):
			raise ConstrainedError(path, 'must be a {}'.format(self.type.__name__))

class DictItem(Item):
	def __init__(self, constrained_keys = (), **kwargs):
		super().__init__(dict, {key.replace('_', '-'): value for key, value in kwargs.items()})
		self.constrained_keys = set(constrained_keys)

	def merge(self, value):
		value = value or {}
		result = {}

		for key in self.default:
			if key == '-others': continue
			result[key] = self.default[key].merge(value.get(key))
		
		for key in set(value) - set(self.default):
			result[key] = self.default['-others'].merge(value[key])

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

	def merge(self, value):
		return self.default

	def verify(self, path, value):
		if value != None and value != self.default:
			raise ConstrainedError(path, 'cannot be changed')

BASE = DictItem(
	metadata = DictItem(
		hash = DictItem(
			type = FixedItem('id'),
		),
		comments = DictItem(
			type = FixedItem('text')
		),
		original_filename = DictItem(
			type = FixedItem('exact-text')
		),
		_others = DictItem(
			type = Item(set(['exact-text', 'text', 'id', 'number', 'keyword', 'datetime']), 'text')
		),
	),
	database_path = Item(str, None),
)

conf = {}

def load(filename):
	try:
		user_config = yaml.load(open(filename, 'r', encoding = 'utf-8'))
	except FileNotFoundError:
		user_config = {}

	BASE.verify(None, user_config)
	conf.update(BASE.merge(user_config))

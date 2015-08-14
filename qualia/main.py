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
from . import common, config, conversion, database
from .lazy_import import lazy_import

# While we import most modules lazily, some things are always needed.
import argparse
import pkg_resources
import sys

lazy_import(globals(), """
	import collections
	import functools
	import os
	import tempfile
	import shutil
""")

## Utility functions
# A decorator that automatically places a checkpoint after its decorated function runs if it does
# not return nonzero or raise an exception.
def auto_checkpoint(func):
	@functools.wraps(func)
	def wrapper(db, args):
		result = func(db, args) or 0

		if result == 0: db.commit()

		return result

	return wrapper

# Simple convenience function that outputs to `stderr` and automatically calls format with the given
# message and args.
def error(message, *args):
	if os.isatty(2):
		print('\033[31m' + message.format(*args) + '\033[0m', file = sys.stderr)
	else:
		print(message.format(*args), file = sys.stderr)

# Core function that outputs a view of the given file. Used by `search` and `show`.
def show_file(db, f, args):
	if args.format == 'filename':
		print(db.get_filename(f))
	elif args.format == 'hash':
		print(f.hash)
	elif args.format == 'long':
		print('{}:'.format(f.short_hash))
		for field in sorted(f.metadata.keys()):
			if not db.fields[field]['shown']: continue
			print('    {}: {}'.format(field, conversion.format_metadata(f, field, f.metadata[field])))
		print()
	elif args.format == 'short_hash':
		print(f.short_hash)

OUTPUT_FORMATS = ['filename', 'short_hash', 'hash', 'long']

## Commands
### Base implementation
def _mapping_argument_type(val):
	parts = val.split('=')

	if len(parts) != 2 or not all(parts):
		raise argparse.ArgumentTypeError('should be of format FROM=TO')

	return tuple(parts)

# This class holds the details for each possible argument to the command.
class Argument:
	def __init__(self, name, *args, **kwargs):
		# While the class is largely a wrapper around `add_argument`, we do some preprocessing for
		# convenience's sake.
		if not name.startswith('-'):
			kwargs.setdefault('metavar', name.upper())

		self.name = name
		self.args = args
		self.kwargs = kwargs
	
	# This adds the given argument to the command's subparser.
	def add_to_subparser(self, subparser):
		subparser.add_argument(
			self.name,
			*self.args,
			**self.kwargs
		)

	def derive(self, **kwargs):
		new_kwargs = dict(self.kwargs)
		new_kwargs.update(kwargs)

		return Argument(self.name, *self.args, **new_kwargs)

# Holds the information and arguments for a given command.
class Command:
	def __init__(self, func, name, help, *arguments, **kwargs):
		self.func = func
		self.name = name
		self.help = help
		self.arguments = arguments
		self.kwargs = kwargs

		Command.known_commands = {}
	
	def add_to_parser(self, subparsers):
		p = subparsers.add_parser(
			self.name,
			help = self.help,
			**self.kwargs
		)
		
		for argument in self.arguments:
			argument.add_to_subparser(p)

		return p

# A command that encapsulates other commands (like `qualia dump journal`).
class WrapperCommand(Command):
	def __init__(self, *args, **kwargs):
		super().__init__(None, *args, **kwargs)

		self.subcommands = {}

	def add_subcommand(self, name, *args, **kwargs):
		def decorator(func):
			cmd = Command(func, name, *args, **kwargs)
			self.subcommands[name] = cmd

			return cmd
		
		return decorator

	def add_to_parser(self, subparsers):
		p = super().add_to_parser(subparsers)

		command_subparsers = p.add_subparsers(
			title = 'subcommands',
			dest = 'subcommand',
			metavar = '<subcommand>',
		)
		
		for _, subcommand in sorted(self.subcommands.items()):
			subcommand.add_to_parser(command_subparsers)

known_commands = {}
def add_command(name, *args, **kwargs):
	def decorator(func):
		cmd = Command(func, name, *args, **kwargs)
		known_commands[name] = cmd

		return cmd
	
	return decorator

def add_wrapper(name, *args, **kwargs):
	cmd = WrapperCommand(name, *args, **kwargs)
	known_commands[name] = cmd

	return cmd

### Common arguments
arg_format = Argument('-f', '--format',
	help = 'Output format',
	dest = 'format',
	choices = OUTPUT_FORMATS,
)

### `add`/`take`
@add_command('add',
	'add an external file to the DB (use \'take\' to move instead of copying)',
	Argument('--restore',
		action = 'store_true',
		help = 'Restore previous metadata for this file',
	),
	Argument('file',
		help = 'External file(s) to add',
		nargs = '+',
		type = argparse.FileType('rb'),
	),
	aliases = ['take'],
)
@auto_checkpoint
def command_add(db, args):
	for sf in args.file:
		try:
			f = db.add_file(sf, args.command == 'take')
			conversion.auto_add_metadata(f, sf.name)
			if args.restore: db.restore_metadata(f)
			db.save(f)
			print('{}: {}'.format(sf.name, f.short_hash))
		except common.FileExistsError: error('{}: identical file in database, not added', sf.name)

### `delete`/`rm`
@add_command('delete',
	'Delete a file',
	Argument('hash',
		help = 'Hashes of file(s) to delete',
		nargs = '+',
	),
	aliases = ['rm'],
)
@auto_checkpoint
def command_delete(db, args):
	for hash in args.hash:
		try:
			db.delete(db.get(hash))
		except common.FileDoesNotExistError: error('{}: does not exist', hash)

### `dump`
wrapper_dump = add_wrapper(
	'dump',
	'Dump raw information from the database',
)

#### `dump journal`
@wrapper_dump.add_subcommand(
	'journal',
	'Dump all checkpoints in YAML format',
)
def subcommand_dump_journal(db, args):
	for checkpoint in db.all_checkpoints():
		print(conversion.format_yaml_checkpoint(checkpoint))

#### `dump metadata`
@wrapper_dump.add_subcommand(
	'metadata',
	'Dump metadata for all files in YAML format',
)
def subcommand_dump_metadata(db, args):
	for f in db.all():
		print(conversion.format_yaml_metadata(f))

### `edit`
@add_command(
	'edit',
	'Edit all of the metadata of a given file',
	Argument('hash',
		help = 'hash of file to edit',
	),
	Argument('-n', '--dry-run',
		help = 'Don\'t save edits to database',
		action = 'store_true',
	),
	Argument('-v', '--verbose',
		action = 'store_true',
		help = 'Show changes to metadata',
	),
)
@auto_checkpoint
def command_edit(db, args):
	try:
		f = db.get(args.hash)

		editable = conversion.format_editable_metadata(f)

		# This plays tricks with process launching and mutual file access that are not safe for
		# those under 18 and, probably, any edge cases. Proceed at your own risk.
		metadata_f = tempfile.NamedTemporaryFile(mode = 'w+t', encoding = 'utf-8')
		metadata_f.write(editable)
		metadata_f.flush()

		# This will eventually need to get abstracted out. This whole process should be, actually,
		# and should deal with cases like backgrounded editors.
		editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'vi'))

		if os.system(editor + ' ' + metadata_f.name) != 0:
			error('could not run {}; please check your settings for $EDITOR or $VISUAL', editor)

		metadata_f.seek(0)
		editable = metadata_f.read()
		metadata_f.close()

		modifications = conversion.parse_editable_metadata(f, editable)

		if args.verbose:
			for field, value in modifications:
				print('changing {} to {}'.format(field, conversion.format_metadata(f, field, value)))

		if not args.dry_run: db.save(f)
	except common.AmbiguousHashError: error('{}: ambiguous hash', args.hash)
	except common.FieldDoesNotExistError as e: error('field "{}" does not exist', e.args[0])
	except common.FieldReadOnlyError as e: error('field "{}" is read only', e.args[0])
	except common.FileDoesNotExistError as e: error('{}: does not exist', e.args[0])
	except common.InvalidFieldValue as e: error('invalid value "{}" for field {}', e.args[1], e.args[0])

### `exists`
@add_command(
	'exists',
	'Check whether a file exists and set exit status accordingly',
	Argument('hash',
		help = 'hash of file to check for',
	),
)
def command_exists(db, args):
	try:
		db.get(args.hash)

		return 0
	except (common.AmbiguousHashError, common.FileDoesNotExistError):
		return 1

### `export`
@add_command(
	'export',
	'Export file contents/metadata',
	Argument('-a', '--all',
		action = 'store_true',
		help = 'Export all files',
	),
	Argument('-m', '--metadata-only',
		action = 'store_true',
		help = 'Only export metadata, not file contents',
	),
	Argument('-o', '--output-filename',
		dest = 'output_file',
		type = argparse.FileType('wb'),
		help = 'Output filename (if not specified, defaults to ./YYYY-MM-DD-HH-MM-SS.qualia'
	),
	Argument('hash',
		help = 'Specific hashes to export',
		nargs = '*',
	),
)
def command_export(db, args):
	try:
		if args.all == bool(args.hash):
			error('must specify either --all or specific hashes to export (but not both)')
			return 1

		conversion.export(db, args.output_file, None if args.all else args.hash, metadata_only = args.metadata_only)
		return 0
	except common.AmbiguousHashError: error('{}: ambiguous hash', e.args[0])
	except common.FileDoesNotExistError as e: error('{}: does not exist', e.args[0])

### `field`
wrapper_field = add_wrapper(
	'field',
	'Change available fields',
)

#### `field list`
@wrapper_field.add_subcommand(
	'list',
	'List available fields',
)
def subcommand_field_list(db, args):
	for field in sorted(db.fields):
		print(field)

### `find-hashes`
@add_command(
	'find-hashes',
	'Print all hashes starting with PREFIX',
	Argument('prefix',
		help = 'prefix to hashes to look for',
	),
)
def command_find_hashes(db, args):
	for hash in db.find_hashes(args.prefix):
		print(hash)

### `import`
@add_command(
	'import',
	'Import a previous export',
	Argument('file',
		help = 'Qualia export file',
		type = argparse.FileType('rb'),
	),
	Argument('-r', '--rename',
		help = 'Field rename on import, can specify multiple',
		action = 'append',
		dest = 'rename',
		metavar = 'FROM=TO',
		type = _mapping_argument_type,
	),
)
def command_import(db, args):
	conversion.import_(db, args.file, renames = dict(args.rename or []))

### `log`
@add_command(
	'log',
	'Print modifications to the database',
)
def command_log(db, args):
	for checkpoint in db.all_checkpoints(order = 'desc'):
		print('#{}: '.format(checkpoint['checkpoint_id']), end = '')

		types = collections.defaultdict(lambda: 0)

		for transaction in checkpoint['transactions']:
			types[transaction['op']] += 1

		print(', '.join('{} "{}"'.format(types[t], t) for t in sorted(types.keys())))

### `search`
@add_command(
	'search',
	'Search files by metadata',
	Argument('query',
		nargs = '+'
	),
	arg_format.derive(
		default = 'short_hash',
	),
	Argument('-l', '--long',
		help = 'Show metadata (default no)',
		dest = 'format',
		action = 'store_const',
		const = 'long'
	),
	Argument('-n', '--limit',
		help = 'Number of results to show',
		type = int,
		default = 10
	),
)
def command_search(db, args):
	for result in db.search(' '.join(args.query), limit = args.limit):
		show_file(db, result, args)

### `set`
@add_command(
	'set',
	'Set metadata for a given file',
	Argument('hash',
		help = 'Hash of file to change',
	),
	Argument('field',
		help = 'Metadata field',
	),
	Argument('value',
		help = 'Metadata value',
	),
)
@auto_checkpoint
def command_set(db, args):
	try:
		f = db.get(args.hash)
		f.set_metadata(args.field, conversion.parse_metadata(f, args.field, args.value))
		db.save(f)

		return 0
	except common.AmbiguousHashError: error('{}: ambiguous hash', args.hash)
	except common.FieldDoesNotExistError: error('field "{}" does not exist', args.field)
	except common.FieldReadOnlyError: error('field "{}" is read only', args.field)
	except common.FileDoesNotExistError: error('{}: does not exist', args.hash)
	except common.InvalidFieldValue: error('invalid value "{}" for field', args.value, args.field)

	return 1

### `show`
@add_command(
	'show',
	'Show metadata for selected files',
	Argument('hash',
		help = 'Hashes of files to show',
		nargs = '+',
	),
	arg_format.derive(
		default = 'long',
	),
	Argument('-l', '--long',
		help = 'Show metadata (default no)',
		dest = 'format',
		action = 'store_const',
		const = 'long'
	),
)
def command_show(db, args):
	for hash in args.hash:
		try:
			f = db.get(hash)
			show_file(db, f, args)

		except common.AmbiguousHashError: error('{}: ambiguous hash', hash)
		except common.FileDoesNotExistError: error('{}: does not exist', hash)

### `set`
@add_command(
	'tag',
	'Add a given tag to a file',
	Argument('hash',
		help = 'Hash of file to change',
	),
	Argument('tag',
		help = 'Tag to add',
	),
)
@auto_checkpoint
def command_tag(db, args):
	try:
		f = db.get(args.hash)

		value = f.metadata.get('tags', '')
		if args.tag not in value.split():
			value += (' ' if value else '') + args.tag
		f.set_metadata('tags', value)
		db.save(f)

		return 0
	except common.AmbiguousHashError: error('{}: ambiguous hash', args.hash)
	except common.FileDoesNotExistError: error('{}: does not exist', args.hash)

	return 1

### `undo`
@add_command(
	'undo',
	'Undo the last checkpoint',
	Argument('checkpoint',
		help = 'Checkpoint to undo (or last)',
		nargs = '?',
	),
)
@auto_checkpoint
def command_undo(db, args):
	try:
		db.undo(args.checkpoint)

		return 0
	except common.CheckpointDoesNotExistError: error('checkpoint {}: does not exist', args.checkpoint)
	except common.UndoFailedError as e: error('could not undo "{}" transaction (no changes done)', e.args[0]['op'])

	return 1

# From: http://stackoverflow.com/a/13429281
#
# This makes sure that the help message for the `command` argument isn't printed. It would be nice
# if it did the same for `subcommand`.
class SubcommandHelpFormatter(argparse.RawDescriptionHelpFormatter):
	def _format_action(self, action):
		parts = super(argparse.RawDescriptionHelpFormatter, self)._format_action(action)
		if action.nargs == argparse.PARSER:
			parts = "\n".join(parts.split("\n")[1:])
		return parts

## Main
def main():
	# Read in terminal size, and store it back into the environment. This might make argparse happy
	# somehow.
	os.environ['COLUMNS'] = str(shutil.get_terminal_size().columns)

	### Plugin loading/argument parsing
	parser = argparse.ArgumentParser(
		prog = 'qualia',
		formatter_class = SubcommandHelpFormatter,
	)

	parser.add_argument('--db-path', '-d',
		help = 'Database path'
	)

	parser.add_argument('--config',
		help = 'Config file path',
		default = config.get_default_path()
	)

	subparsers = parser.add_subparsers(
		title = 'commands',
		dest = 'command',
		metavar = '<command>',
	)

	for ep in pkg_resources.iter_entry_points(group = 'qualia.plugins'):
		ep.load()(
			toplevel_parser = parser,
			commands = subparsers,
		)

	### Commands
	for _, command in sorted(known_commands.items()):
		command.add_to_parser(subparsers)

	args = parser.parse_args()

	### Setup
	# The global user config has to be loaded, followed by the database-specific config (as the
	# former may change the default database location).
	try:
		config.conf = config.load(args.config, config.CONF_BASE)
		db_path = args.db_path or config.conf['database-path'] or database.get_default_path()
		config.conf = config.load(os.path.join(db_path, 'config.yaml'), config.CONF_BASE, start = config.conf)

		# Then, finally, we can load the database.
		db = database.Database(db_path)
	except config.ConstrainedError as e:
		error('error in configuration file: {}', ('{}: {}'.format(*e.args)) if e.args[0] else e.args[1])
		sys.exit(1)
	except common.FieldConfigChangedError as e:
		error('Configuration for field `{}` changed or removed after adding it to files; database is read-only', e.args[0])
		db = database.Database(db_path, read_only = True)

	### Running command
	# `args.command` should be limited to the defined subcommands, but there's not much risk here
	# anyway.
	if 'subcommand' in args:
		return_code = known_commands[args.command].subcommands[args.subcommand].func(db, args) or 0
	else:
		return_code = known_commands[args.command].func(db, args) or 0
	db.close()

	sys.exit(return_code)

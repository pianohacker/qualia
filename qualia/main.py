## Imports
from . import common, config, conversion, database

import argparse
import os
import shutil
import sys

## Utility functions
def error(message, *args):
	print('qualia:', message.format(*args), file = sys.stderr)

def show_file(db, f, args):
	if args.format == 'filename':
		print(db.get_filename(f))
	elif args.format == 'hash':
		print(f.hash)
	elif args.format == 'long':
		print('{}:'.format(f.short_hash))
		for field in sorted(f.metadata.keys()):
			print('    {}: {}'.format(field, f.metadata[field]))
		print()
	elif args.format == 'short_hash':
		print(f.short_hash)

OUTPUT_FORMATS = ['filename', 'short_hash', 'hash', 'long']

## Commands
### `add`/`take`
def command_add(db, args):
	for sf in args.file:
		try:
			f = db.add_file(sf, args.command == 'take')
			conversion.auto_add_metadata(f, sf.name)
			db.save(f)
			print('{}: {}'.format(sf.name, f.short_hash))
		except common.FileExistsError:
			error('{}: identical file in database, not added', sf.name)

### `delete`/`rm`
def command_delete(db, args):
	for hash in args.hash:
		try:
			db.delete(db.get(hash))
		except common.FileDoesNotExistError:
			error('{}: does not exist', hash)

### `exists`
def command_exists(db, args):
	try:
		db.get(args.hash)

		return 0
	except (common.AmbiguousHashError, common.FileDoesNotExistError):
		return 1

### `exists`
def command_find_hashes(db, args):
	for hash in db.find_hashes(args.prefix):
		print(hash)

### `search`
def command_search(db, args):
	for result in db.search(' '.join(args.query), limit = args.limit):
		show_file(db, result, args)

### `set`
def command_set(db, args):
	try:
		f = db.get(args.hash)
		f.set_metadata(args.field, conversion.parse_metadata(args.field, args.value))
		db.save(f)
	except common.AmbiguousHashError: error('{}: ambiguous hash', args.hash)
	except common.FieldDoesNotExistError: error('field "{}" does not exist', args.field)
	except common.FieldReadOnlyError: error('field "{}" is read only', args.field)
	except common.FileDoesNotExistError: error('{}: does not exist', args.hash)
	except common.InvalidFieldValue: error('invalid value "{}" for field', args.value, args.field)

### `show`
def command_show(db, args):
	for hash in args.hash:
		try:
			f = db.get(hash)
			show_file(db, f, args)

		except common.AmbiguousHashError: error('{}: ambiguous hash', hash)
		except common.FileDoesNotExistError: error('{}: does not exist', hash)

# From http://stackoverflow.com/a/13429281
class SubcommandHelpFormatter(argparse.RawDescriptionHelpFormatter):
	def _format_action(self, action):
		parts = super(argparse.RawDescriptionHelpFormatter, self)._format_action(action)
		if action.nargs == argparse.PARSER:
			parts = "\n".join(parts.split("\n")[1:])
		return parts

def main():
	# Read in terminal size
	os.environ['COLUMNS'] = str(shutil.get_terminal_size().columns)

	parser = argparse.ArgumentParser(
		prog = 'qualia',
		formatter_class = SubcommandHelpFormatter,
	)

	parser.add_argument('--db',
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

	p = subparsers.add_parser(
		'add',
		aliases = ['take'],
		help = 'add an external file to the DB (use \'take\' to move instead of copying)',
	)
	p.add_argument('file',
		help = 'External file(s) to add',
		metavar = 'FILE',
		nargs = '+',
		type = argparse.FileType('rb'),
	)

	p = subparsers.add_parser(
		'delete',
		aliases = ['rm'],
		help = 'Delete a file',
	)
	p.add_argument('hash',
		help = 'Hashes of file(s) to delete',
		metavar = 'HASH',
		nargs = '+',
	)
	p = subparsers.add_parser(
		'exists',
		help = 'Check whether a file exists and set exit status accordingly',
	)
	p.add_argument('hash',
		help = 'hash of file to check for',
		metavar = 'HASH',
	)

	p = subparsers.add_parser(
		'find-hashes',
		help = 'Print all hashes starting with PREFIX',
	)
	p.add_argument('prefix',
		help = 'prefix to hashes to look for',
		metavar = 'PREFIX',
	)

	p = subparsers.add_parser(
		'search',
		help = 'Search files by metadata',
	)
	p.add_argument('query',
		metavar = 'QUERY',
		nargs = '+'
	)
	p.add_argument('-f', '--format',
		help = 'Output format',
		dest = 'format',
		choices = OUTPUT_FORMATS,
		default = 'short_hash',
	)
	p.add_argument('-l', '--long',
		help = 'Show metadata (default no)',
		dest = 'format',
		action = 'store_const',
		const = 'long'
	)
	p.add_argument('-n', '--limit',
		help = 'Number of results to show',
		type = int,
		default = 10
	)

	p = subparsers.add_parser(
		'set',
		help = 'Set metadata for a given file',
	)
	p.add_argument('hash',
		help = 'Hash of file to change',
		metavar = 'HASH',
	)
	p.add_argument('field',
		help = 'Metadata field',
		metavar = 'FIELD',
	)
	p.add_argument('value',
		help = 'Metadata value',
		metavar = 'VALUE',
	)

	p = subparsers.add_parser(
		'show',
		help = 'Show metadata for selected files',
	)
	p.add_argument('hash',
		help = 'Hashes of files to show',
		metavar = 'HASH',
		nargs = '+',
	)
	p.add_argument('-f', '--format',
		help = 'Output format',
		dest = 'format',
		choices = OUTPUT_FORMATS,
		default = 'long',
	)
	p.add_argument('-l', '--long',
		help = 'Show metadata (default no)',
		dest = 'format',
		action = 'store_const',
		const = 'long'
	)

	args = parser.parse_args()

	config.load(args.config)
	print(__import__('yaml').dump(config.conf))
	db_path = args.db or config.conf['database-path'] or database.get_default_path()
	config.load(os.path.join(db_path, 'config.yaml'))
	print(__import__('yaml').dump(config.conf))
	sys.exit(0)
	db = database.Database(db_path)

	# `args.command` should be limited to the defined subcommands, but there's not much risk here
	# anyway.
	sys.exit(globals()['command_' + args.command.replace('-', '_')](db, args) or 0)

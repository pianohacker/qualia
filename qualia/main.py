## Imports
from . import database

import argparse
import os
import shutil
import sys

## Commands
### `add`/`take`
def command_add(db, args):
	for sf in args.file:
		try:
			f = db.add_file(sf, args.command == 'take')
			f.import_fs_metadata(sf.name)
			db.save(f)
			print('{}: {}'.format(sf.name, f.short_hash))
		except database.FileExistsError:
			print('{}: identical file in database, not added'.format(sf.name))

### `delete`/`rm`
def command_delete(db, args):
	for hash in args.hash:
		try:
			db.delete(db.get(hash))
		except database.FileDoesNotExistError:
			print('{}: does not exist'.format(hash))

### `exists`
def command_exists(db, args):
	try:
		db.get(args.hash)

		return 0
	except (database.AmbiguousHashError, database.FileDoesNotExistError):
		return 1

### `exists`
def command_find_hashes(db, args):
	for hash in db.find_hashes(args.prefix):
		print(hash)

### `show`
def command_show(db, args):
	for hash in args.hash:
		try:
			f = db.get(hash)
			print('{}:'.format(f.short_hash))
			for key, value in f.metadata.items():
				print('    {}: {}'.format(key, value))
		except database.AmbiguousHashError:
			print('{}: ambiguous hash'.format(hash))
		except database.FileDoesNotExistError:
			print('{}: does not exist'.format(hash))

		print()

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
		help = 'Database path',
		default = database.get_default_path()
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
		'show',
		help = 'Show metadata for selected files',
	)
	p.add_argument('hash',
		help = 'Hashes of files to show',
		metavar = 'HASH',
		nargs = '+',
	)

	args = parser.parse_args()

	db = database.Database(args.db)

	sys.exit(globals()['command_' + args.command.replace('-', '_')](db, args) or 0)

import argparse

def main():
	parser = argparse.ArgumentParser(prog = 'qualia')

	subparsers = parser.add_subparsers(help = 'subcommand')

	parser_add = subparsers.add_parser('add', help = 'add a file')
	parser_add.add_argument('file',
		help = 'File(s) to add',
		metavar = 'FILE',
		nargs = '+',
		type = argparse.FileType('rb'),
	)

	args = parser.parse_args()

# Qualia

Qualia is a command-line tool to manage a repository of files with rich, searchable
metadata.

Notable features:

  * Robust, error-proof metadata storage, supporting rollback/undo for most operations
  * Fast, simple searching of metadata
  * Import/export/backup
  * Automatic importing of certain kinds of metadata

Things Qualia can't do (yet):

  * Change the contents of a file after being added.
  * Synchronize the files/repositories it manages to another computer. It should be possible to
    place the Qualia repository in a Dropbox/Owncloud folder, however.
  * Full-text search of text documents.

Example use cases:

  * A large set of wallpapers, with searching by tag/image size/description/etc.
  * A library of ebooks, with searching by author/title/etc.

## Dependencies

  * Python 3.3 or greater
  * [Whoosh](https://pythonhosted.org/Whoosh/)
  * Linux (may work under Windows/OS X, but has not been tested)

## Setup

To begin using Qualia, clone the repository and run `sudo python3 setup.py install` to install the
necessary libraries and executables.

Then, start adding files to Qualia. Your repository will be automatically created under
`~/.local/share/qualia`.

	$ qualia add example.jpg potato.jpg
	example.jpg: 9918
	potato.jpg: 706f

The `9918` and `706f` next to each of the files are their identifiers, generated from a hash of the
files' contents. You can use these identifiers in a number of commands:

	$ qualia show 9918
	file-modified-at: 2014-11-17 11:45:38.964989
	filename: /home/feoh3/p/qualia/example.jpg
	image.height: 1020
	image.width: 1280
	imported-at: 2015-05-19 17:21:28.005271
	magic.mime-type: image/jpeg
	$ qualia tag 9918 wallpaper
	$ qualia search tag:wallpaper
	9918

The full identifiers are much longer (for the above file,
`991899f3190a6c753927d176995238d101470e65e6b0732b05ac2aad82ec1e57ea1232584a18b3f65980c3c144f75e9e5181808fbe28715567d91338185cfdc4`)
but you can use the shortest unambiguous version of this identifier. Qualia prints the shortest
version it can find when the file is added or displayed.

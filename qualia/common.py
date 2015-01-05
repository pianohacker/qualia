# These are common exceptions that can be raised by any of the various components of the database
# code. As putting them in `qualia.database` would raise circular-dependency issues for `.journal`
# and `.search`, they live here.

## Exceptions
# This is raised on an attempt to look up an ambiguous short hash (one that could complete to two or
# more different full hashes).
class AmbiguousHashError(Exception):
	pass

class CheckpointDoesNotExistError(Exception):
	pass

# As the search library cannot change the type of a field after it is created, this is raised if the
# configured type of a field does not match that in the search index schema.
class FieldConfigChangedError(Exception):
	pass

# The user attempted to change a read-only field.
class FieldReadOnlyError(Exception):
	pass

class FileDoesNotExistError(Exception):
	pass

class FileExistsError(Exception):
	pass

class FieldDoesNotExistError(Exception):
	pass

class InvalidFieldValue(Exception):
	pass

class UndoFailedError(Exception):
	pass

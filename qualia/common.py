# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
# 
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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

class DatabaseReadOnlyError(Exception):
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

## Utility functions
# Generates a dict and a decorator that inserts items into that dict. Useful for handler registries.

def registry_with_decorator():
	registry = dict()

	def decorator(key):
		def inner(func):
			registry[key] = func

			return func

		return inner

	return registry, decorator


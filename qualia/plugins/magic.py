# Copyright (c) 2020 Jesse Weaver.
#
# This file is part of Qualia.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from qualia import config

def register(**kwargs):
	config.DB_STATE_BASE['fields']['magic.mime-type'] = config.DerivedDictItem(config.FIELD_ITEM_BASE,
		'type', config.FixedItem('exact-text'),
		'aliases', ['mime', 'dc.format'],
	)

magic_db = None

def auto_add_magic(f, original_filename):
	global magic_db

	if magic_db is None:
		import magic

		magic_db = magic.open(magic.SYMLINK | magic.COMPRESS | magic.MIME_TYPE)
		magic_db.load()

	f.set_metadata('magic.mime-type', magic_db.file(original_filename), 'auto')

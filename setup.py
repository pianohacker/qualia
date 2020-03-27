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

from setuptools import setup, find_packages

setup(
	name = "Qualia",
	version = "0.1",
	packages = find_packages(),

	entry_points={
		'console_scripts': [
			'qualia = qualia.main:main',
		],
		'qualia.plugins': [
			'image = qualia.plugins.image:register',
			'magic = qualia.plugins.magic:register',
		],
		'qualia.auto_metadata_importers': [
			'image = qualia.plugins.image:auto_add_image',
			'magic = qualia.plugins.magic:auto_add_magic',
		],
	},

	install_requires = [
		'file-magic',
		'Pillow',
	]
)

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
	version = "0.2",
	packages = find_packages(),

	install_requires = [
		'behave',
		'pyhamcrest',
		'parsy',
		'rure',
	]
)

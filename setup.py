from setuptools import setup, find_packages

setup(
	name = "Qualia",
	version = "0.1",
	packages = find_packages(),

	entry_points={
		'console_scripts': [
			'qualia = qualia.main:main',
		],
		'qualia.auto_metadata_importers': [
			'image = qualia.plugins.image:auto_add_image',
			'magic = qualia.plugins.magic:auto_add_magic',
		]
	},

	install_requires = [
		'Magic-file-extensions',
		'Pillow',
	]
)

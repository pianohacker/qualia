from setuptools import setup, find_packages

setup(
	name = "Qualia",
	version = "0.1",
	packages = find_packages(),
	entry_points={
		'console_scripts': [
			'qualia = qualia.main:main',
		],
	}
)

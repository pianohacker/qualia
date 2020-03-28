from behave import given, when

from os import path
import qualia
import shutil
import tempfile

def _get_temp_directory(context):
	dir = tempfile.mkdtemp(prefix = 'qualia-tests-')

	context.add_cleanup(lambda: shutil.rmtree(dir))

	return dir

@given('an empty database')
def step_impl(context):
	context.db_dir = _get_temp_directory(context)

	context.db = qualia.open(path.join(context.db_dir, 'empty.qualia'))

@when('we close the database')
def step_impl(context):
	context.db.close()

@when('we reopen the database')
def step_impl(context):
	context.db = qualia.open(path.join(context.db_dir, 'empty.qualia'))

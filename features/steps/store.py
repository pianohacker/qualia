from behave import given, when

from os import path
import qualia
import shutil
import tempfile

def _get_temp_directory(context):
	dir = tempfile.mkdtemp(prefix = 'qualia-tests-')

	context.add_cleanup(lambda: shutil.rmtree(dir))

	return dir

@given('an empty store')
def step_impl(context):
	context.store_dir = _get_temp_directory(context)

	context.store = qualia.open(path.join(context.store_dir, 'empty.qualia'))

@when('we close the store')
def step_impl(context):
	context.store.close()

@when('we reopen the store')
def step_impl(context):
	context.store = qualia.open(path.join(context.store_dir, 'empty.qualia'))

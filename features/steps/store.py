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

@given('a store seeded with numbers')
def step_impl(context):
	context.execute_steps('given an empty store')

	context.store.add(name = 'first', value = 1, ordinal = "yes")
	context.store.add(name = 'second', value = 2, ordinal = "yes")
	context.store.add(name = 'third', value = 3, ordinal = "yes")
	context.store.add(name = 'fourth', value = 4, ordinal = "yes")
	context.store.add(name = 'one', value = 1, ordinal = "no")
	context.store.add(name = 'two', value = 2, ordinal = "no")
	context.store.add(name = 'three', value = 3, ordinal = "no")
	context.store.add(name = 'four', value = 4, ordinal = "no")
	context.store.commit()

@when('commit')
def step_impl(context):
	context.store.commit()

@when('we undo')
def step_impl(context):
	context.store.undo()

@when('we close the store')
def step_impl(context):
	context.store.close()

@when('we reopen the store')
def step_impl(context):
	context.store = qualia.open(path.join(context.store_dir, 'empty.qualia'))

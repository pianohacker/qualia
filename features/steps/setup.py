from behave import given

from os import path
import shutil
import qualia
import tempfile

def _get_temp_directory(context):
	dir = tempfile.mkdtemp(prefix = 'qualia-tests-')

	context.add_cleanup(lambda: shutil.rmtree(dir))

	return dir

@given('an empty database')
def step_impl(context):
	context.db_dir = _get_temp_directory(context)

	context.db = qualia.open(path.join(context.db_dir, 'empty.qualia'))

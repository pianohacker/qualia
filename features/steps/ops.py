from behave import when

from os import path
import qualia

@when('we list the objects in that database')
def step_impl(context):
	context.result = context.db.select()

@when('we close the database')
def step_impl(context):
	context.db.close()

@when('we reopen the database')
def step_impl(context):
	context.db = qualia.open(path.join(context.db_dir, 'empty.qualia'))

@when('we add "{name:w}" to the database')
def step_impl(context, name):
	context.db.add({"name": name})

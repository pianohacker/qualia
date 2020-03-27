from behave import when

@when('we list the objects in that database')
def step_impl(context):
	context.result = context.db.select()

@when('we add "{name:w}" to the database')
def step_impl(context, name):
	context.db.add({"name": name})

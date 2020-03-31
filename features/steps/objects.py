from behave import when

@when('we list the objects in that database')
def step_impl(context):
	context.result = list(context.db.all())

@when('we add "{name:w}" to the database')
def step_impl(context, name):
	context.db.add({"name": name})

@when('we delete "{name:w}" from the database')
def step_impl(context, name):
	context.db.select({"name": name}).delete()

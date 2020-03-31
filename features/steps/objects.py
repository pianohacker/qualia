from behave import when

@when('we list the objects')
def step_impl(context):
	context.result = list(context.db.all())

@when('we add the object "{name:w}"')
def step_impl(context, name):
	context.db.add(name = name)

@when('we delete the object "{name:w}"')
def step_impl(context, name):
	context.db.select(name = name).delete()

@when('we rename the object "{orig_name:w}" to "{new_name:w}"')
def step_impl(context, orig_name, new_name):
	context.db.select(name = orig_name).update(name = new_name)

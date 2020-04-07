from behave import use_step_matcher, when
import qualia

@when('we list the objects')
def step_impl(context):
	context.result = list(context.store.all())

@when('we add the object "{name:w}"')
def step_impl(context, name):
	context.store.add(name = name)

@when('we delete the object "{name:w}"')
def step_impl(context, name):
	context.store.select(name = name).delete()

@when('we rename the object "{orig_name:w}" to "{new_name:w}"')
def step_impl(context, orig_name, new_name):
	context.store.select(name = orig_name).update(name = new_name)

use_step_matcher('re')
@when('we query for `(?P<q>[^`]*)`')
def step_impl(context, q):
	context.result = list(context.store.query(q))

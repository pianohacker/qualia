from behave import use_step_matcher, when
import qualia
import re

@when('we list the objects')
def step_impl(context):
	context.result = list(context.store.all())

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

PROPERTY_WITH_GROUPS = r'([\w-]+):\s*("[^"]*"|[^,]*)'
PROPERTY = r'[\w-]+:\s*(?:"[^"]*"|[^,]*)'

@when(r'we add the object `(?P<object_description>' + PROPERTY + '(?:,\s*' + PROPERTY + ')*)`')
def step_impl(context, object_description):
	properties = re.findall(PROPERTY_WITH_GROUPS, object_description)
	context.store.add(**dict((k, v.strip('"')) for (k, v) in properties))

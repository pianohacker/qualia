from behave import then, use_step_matcher
from hamcrest import *

@then('we see {number:d} objects')
def step_impl(context, number):
	assert_that(context.result, has_length(number))

use_step_matcher('re')
@then('one of those objects is called "(?P<name>[^"]*)"')
def step_impl(context, name):
	assert_that(context.result, has_item(has_entry('name', name)))

@then('`(?P<step>[^`]*)` should fail like "(?P<part_of_error>[^"]*)"')
def step_impl(context, step, part_of_error):
	assert_that(
		calling(context.execute_steps).with_args(step),
		raises(Exception, pattern = ".*" + part_of_error + ".*")
	)

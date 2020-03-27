from behave import then
from hamcrest import *

@then('we see {number:d} objects')
def step_impl(context, number):
	assert_that(context.result, has_length(number))

@then('one of those objects is called "{name:w}"')
def step_impl(context, name):
	assert_that(context.result, has_item(has_entry('name', name)))

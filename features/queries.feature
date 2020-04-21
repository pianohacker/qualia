Feature: query syntax
	Background:
		Given an empty store
		When we add the object `name: first, value: 1, ordinal: yes`
		 And we add the object `name: second, value: 2, ordinal: yes`
		 And we add the object `name: third, value: 3, ordinal: yes`
		 And we add the object `name: fourth, value: 4, ordinal: yes`
		 And we add the object `name: one, value: 1, ordinal: no`
		 And we add the object `name: two, value: 2, ordinal: no`
		 And we add the object `name: three, value: 3, ordinal: no`
		 And we add the object `name: four, value: 4, ordinal: no`
		 And we add the object `name: five hundred, value: 500, ordinal: no`
		 And we add the object `name: " space six", value: 6, ordinal: no`

	Scenario: An empty query should return all objects
		When we query for ``
		Then we see 10 objects

	Scenario: A query for a full word should match
		When we query for `name: one`
		Then we see 1 objects
		 And one of those objects is called "one"

	Scenario: A query for a number should match
		When we query for `value: 1`
		Then we see 2 objects
		 And one of those objects is called "first"
		 And one of those objects is called "one"

	Scenario: A query for multiple properties should combine as AND
		When we query for `value: 1, ordinal: yes`
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: Queries with extra whitespace should work the same
		When we query for ` name :  one  `
		Then we see 1 objects
		 And one of those objects is called "one"

	Scenario: Queries should match a single word within phrase
		When we query for `name: hundred`
		Then we see 1 objects
		 And one of those objects is called "five hundred"

		When we query for `name: space`
		Then we see 1 objects
		 And one of those objects is called " space six"

	Scenario: Exact queries should only match the exact text
		When we query for `name: exactly one`
		Then we see 1 objects
		 And one of those objects is called "one"

		When we query for `name: exactly hundred`
		Then we see 0 objects

		When we query for `name: exactly five hundred`
		Then we see 1 objects
		 And one of those objects is called "five hundred"

	Scenario: Exact queries should be specific about whitespace
		When we query for `name: exactly "space six"`
		Then we see 0 objects

		When we query for `name: exactly " space six"`
		Then we see 1 objects
		 And one of those objects is called " space six"

	Scenario: Range queries should match numerically
		When we query for `value: between 1 and 3, ordinal: yes`
		Then we see 3 objects
		 And one of those objects is called "first"
		 And one of those objects is called "second"
		 And one of those objects is called "third"

	Scenario: It should be possible to query by object ID
		When we query for `object_id: 1`
		Then we see 1 objects
		 And one of those objects is called "first"

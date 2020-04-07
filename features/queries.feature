Feature: query syntax
	Scenario: An empty query should return all objects
		Given a store seeded with numbers
		When we query for ``
		Then we see 8 objects

	Scenario: A query for a full word should match
		Given a store seeded with numbers
		When we query for `name: one`
		Then we see 1 objects
		 And one of those objects is called "one"

	Scenario: A query for a number should match
		Given a store seeded with numbers
		When we query for `value: 1`
		Then we see 2 objects
		 And one of those objects is called "first"
		 And one of those objects is called "one"

	Scenario: A query for multiple properties should combine as AND
		Given a store seeded with numbers
		When we query for `value: 1 ordinal: yes`
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: Queries with extra whitespace should work the same
		Given a store seeded with numbers
		When we query for ` name:  one  `
		Then we see 1 objects
		 And one of those objects is called "one"

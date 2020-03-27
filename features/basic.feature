Feature: Basic operation
	Scenario: Empty database should be empty
		Given an empty database
		When we list the objects in that database
		Then we see 0 objects

	Scenario: A newly added object should show up
		Given an empty database
		When we add "spam" to the database
		 And we list the objects in that database
		Then we see 1 objects
		 And one of those objects is called "spam"

	Scenario: Objects should persist
		Given an empty database
		When we add "foobar" to the database
		 And we close the database
		 And we reopen the database
		 And we list the objects in that database
		Then we see 1 objects
		 And one of those objects is called "foobar"

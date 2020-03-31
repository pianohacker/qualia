Feature: Basic operation
	Scenario: Empty store should be empty
		Given an empty store
		When we list the objects
		Then we see 0 objects

	Scenario: A newly added object should show up
		Given an empty store
		When we add the object "spam"
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "spam"

	Scenario: Objects should persist
		Given an empty store
		When we add the object "foobar"
		 And we close the store
		 And we reopen the store
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "foobar"

	Scenario: Deletion
		Given an empty store

		When we add the object "James"
		 And we add the object "Jimmy"
		 And we delete the object "James"
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "Jimmy"

	Scenario: Deletion
		Given an empty store

		When we add the object "James"
		 And we rename the object "James" to "Jimmy"
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "Jimmy"

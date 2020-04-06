Feature: undoing operations
	Scenario: undoing addition
		Given an empty store
		When we add the object "first"
		 And commit
		 And we add the object "second"
		 And commit
		 And we list the objects
		Then we see 2 objects

		When we undo
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: undoing deletion
		Given an empty store
		When we add the object "first"
		 And we add the object "second"
		 And commit
		 And we delete the object "first"
		 And commit
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "second"

		When we undo
		 And we list the objects
		Then we see 2 objects
		 And one of those objects is called "first"
		 And one of those objects is called "second"

	Scenario: undoing modification
		Given an empty store
		When we add the object "first"
		 And commit
		 And we rename the object "first" to "second"
		 And commit
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "second"

		When we undo
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: undoing deletion and modification in the right order
		Given an empty store
		When we add the object "first"
		 And commit
		 And we rename the object "first" to "second"
		 And we delete the object "second"
		 And commit
		 And we list the objects
		Then we see 0 objects

		When we undo
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: undoing modification
		Given an empty store
		When we add the object "first"
		 And commit
		 And we rename the object "first" to "second"
		 And commit
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "second"

		When we undo
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: undoing multiple operations
		Given an empty store
		When we add the object "first"
		 And commit
		 And we add the object "second"
		 And commit
		 And we add the object "third"
		 And commit
		 And we list the objects
		Then we see 3 objects

		When we undo
		 And we list the objects
		Then we see 2 objects
		 And one of those objects is called "first"
		 And one of those objects is called "second"

		When we undo
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: undo should persist
		Given an empty store
		When we add the object "first"
		 And commit
		 And we add the object "second"
		 And commit
		 And we undo
		 And we close the store
		 And we reopen the store
		 And we list the objects
		Then we see 1 objects
		 And one of those objects is called "first"

	Scenario: undoing the first operation
		Given an empty store
		When we add the object "first"
		 And commit
		 And we add the object "second"
		 And commit
		 And we undo
		 And we undo
		 And we list the objects
		Then we see 0 objects

	Scenario: undoing when there's nothing to undo
		Given an empty store
		When we undo
		# Then it does not fail

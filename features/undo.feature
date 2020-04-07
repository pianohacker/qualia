Feature: Undoing operations
	Scenario: Undoing addition should remove an object
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

	Scenario: Undoing deletion should add an object
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

	Scenario: Undoing modification should restore the original object
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

	Scenario: Undoing deletion and modification must occur in the right order
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

	Scenario: Undoing multiple operations should progressively restore state
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

	Scenario: Undo should persist after a close/reopen
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

	Scenario: Undoing the first operation should succeed
		Given an empty store
		When we add the object "first"
		 And commit
		 And we add the object "second"
		 And commit
		 And we undo
		 And we undo
		 And we list the objects
		Then we see 0 objects

	Scenario: Undoing when there's nothing to undo should silently succeed
		Given an empty store
		When we undo
		# Then it does not fail

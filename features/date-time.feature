Feature: date/time support
	Background:
		Given an empty store
		When we add the following objects:
			| name | birthday   |
			| Joe  | 1990-10-11 |
			| Jim  | 1991-09-11 |
			| Bob  | 1992-11-09 |
	Scenario:
		When we query for `birthday: between dates 1991-01-01 and 1991-11-30`
		Then we see 1 objects
		 And one of those objects is called "Jim"

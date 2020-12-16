use crate::object::PropValue;
use crate::query::QueryNode;
use crate::query::QueryNode::*;

pub enum QueryBuilder {
    Empty,
    Single(QueryNode),
    And(Vec<QueryNode>),
}

pub const Q: QueryBuilder = QueryBuilder::Empty;

impl QueryBuilder {
    pub fn add(self, node: QueryNode) -> Self {
        match self {
            QueryBuilder::Empty => QueryBuilder::Single(node),
            QueryBuilder::Single(prev_node) => QueryBuilder::And(vec![prev_node, node]),
            QueryBuilder::And(mut nodes) => {
                nodes.push(node);
                QueryBuilder::And(nodes)
            }
        }
    }

    pub fn id(self, value: impl Into<i64>) -> Self {
        self.add(PropEqual {
            name: "object-id".into(),
            value: value.into().into(),
        })
    }

    pub fn equal(self, name: impl Into<String>, value: impl Into<PropValue>) -> Self {
        self.add(PropEqual {
            name: name.into(),
            value: value.into(),
        })
    }

    pub fn like(self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.add(PropLike {
            name: name.into(),
            value: value.into(),
        })
    }

    pub fn build(self) -> QueryNode {
        match self {
            QueryBuilder::Single(node) => node,
            QueryBuilder::And(nodes) => And(nodes),
            QueryBuilder::Empty => Empty,
        }
    }
}

impl Into<QueryNode> for QueryBuilder {
    fn into(self) -> QueryNode {
        self.build()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    macro_rules! builder_test {
        ($description:expr, $actual:expr, $expected:expr $(,)?) => {
            ($description, $actual, $expected)
        };
    }

    #[test]
    fn queries_build_correctly() {
        let tests = [
            builder_test!("empty query", Q.build(), Empty {}),
            builder_test!(
                "string equal",
                Q.equal("name", "value").build(),
                PropEqual {
                    name: "name".to_string(),
                    value: "value".into(),
                },
            ),
            builder_test!(
                "number equal",
                Q.equal("name", 42).build(),
                PropEqual {
                    name: "name".to_string(),
                    value: 42.into(),
                },
            ),
            builder_test!(
                "object-id equal",
                Q.id(42).build(),
                PropEqual {
                    name: "object-id".to_string(),
                    value: 42.into(),
                },
            ),
            builder_test!(
                "simple word like",
                Q.like("name", "phrase").build(),
                PropLike {
                    name: "name".to_string(),
                    value: "phrase".to_string(),
                },
            ),
            builder_test!(
                "anded queries",
                Q.equal("name1", "value1")
                    .equal("name2", "value2")
                    .equal("name3", "value3")
                    .build(),
                And(vec![
                    PropEqual {
                        name: "name1".to_string(),
                        value: "value1".into(),
                    },
                    PropEqual {
                        name: "name2".to_string(),
                        value: "value2".into(),
                    },
                    PropEqual {
                        name: "name3".to_string(),
                        value: "value3".into(),
                    },
                ]),
            ),
        ];

        for (description, actual_query, expected_query) in &tests {
            assert_eq!(expected_query, actual_query, "{}", description);
        }
    }
}

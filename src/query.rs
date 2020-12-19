use rusqlite::ToSql;

use crate::object::PropValue;

/// A node within a query tree.
///
/// For all but advanced cases, [`QueryBuilder`](crate::query_builder::QueryBuilder) should be used
/// (via [`Q`](crate::query_builder::Q)) rather than creating QueryNode objects directly.
#[derive(Debug, PartialEq)]
pub enum QueryNode {
    /// Will match all objects.
    Empty,

    /// Will match objects that have the given property with exactly the given value.
    PropEqual { name: String, value: PropValue },

    /// Will match objects that the given property with contents matching the given pattern.
    ///
    /// The pattern is composed of a set of words, each one of which must exist in order (though
    /// there may be other words in between). Each word may be just an alphanumeric word or may
    /// contain one or more `*`'s, each of which will match zero or more characters.
    ///
    /// For example, the following patterns will match the property value `"why the lucky stiff"`:
    ///   * `why`
    ///   * `why lucky`
    ///   * `why luck*`
    ///   * `why luck*y`
    ///   * `*tiff`
    ///   * `the *ck*`
    ///
    /// while the following patterns will not:
    ///   * `wh`
    ///   * `lucky why`
    ///   * `matts`
    ///   * `wha*`
    PropLike { name: String, pattern: String },

    /// Will match all objects that match each of the contained criteria.
    And(Vec<QueryNode>),
}

macro_rules! vec_params {
    ($($param:expr),* $(,)?) => {
        vec![$(Box::new($param) as Box<dyn ToSql>),*]
    };
}

impl ToSql for PropValue {
    fn to_sql(&self) -> std::result::Result<rusqlite::types::ToSqlOutput<'_>, rusqlite::Error> {
        match self {
            PropValue::Number(n) => n.to_sql(),
            PropValue::String(s) => s.to_sql(),
        }
    }
}

impl QueryNode {
    pub(crate) fn to_sql_clause(&self) -> (String, Vec<Box<dyn ToSql>>) {
        match self {
            QueryNode::Empty => ("1=1".to_string(), vec_params![]),
            QueryNode::PropEqual { name, value } => Self::equal_to_sql_clause(name, value),
            QueryNode::PropLike { name, pattern } => Self::like_to_sql_clause(name, pattern),
            QueryNode::And(nodes) => Self::and_to_sql_clause(nodes),
        }
    }

    fn equal_to_sql_clause(name: &String, value: &PropValue) -> (String, Vec<Box<dyn ToSql>>) {
        if name == "object-id" {
            return ("object_id = ?".to_string(), vec_params![value.clone()]);
        }

        let cast_type = match value {
            PropValue::String(_) => "TEXT",
            PropValue::Number(_) => "NUMBER",
        };

        (
            format!(
                "CAST(json_extract(properties, \"$.{}\") AS {}) = ?",
                name, cast_type
            )
            .to_string(),
            vec_params![value.clone()],
        )
    }

    fn like_to_sql_clause(name: &String, pattern: &String) -> (String, Vec<Box<dyn ToSql>>) {
        let words = pattern.split(" ").filter(|word| word != &"");
        let wrapped_words: Vec<String> = words
            .map(|word| {
                let pieces = word.split("*");
                let quoted_pieces: Vec<String> = pieces.map(regex::escape).collect();
                format!(r"\b{}\b", quoted_pieces.join(r"\w*"))
            })
            .collect();
        let wrapped_words_phrase = wrapped_words.join(r".*?");

        (
            format!(
                "CAST(json_extract(properties, \"$.{}\") AS TEXT) REGEXP ?",
                name
            )
            .to_string(),
            vec_params![format!(r"(?i){}", wrapped_words_phrase).to_string()],
        )
    }

    fn and_to_sql_clause(nodes: &Vec<QueryNode>) -> (String, Vec<Box<dyn ToSql>>) {
        let (clauses, param_vecs): (Vec<_>, Vec<_>) =
            nodes.iter().map(|node| node.to_sql_clause()).unzip();

        (
            clauses.join(" AND "),
            param_vecs.into_iter().flatten().collect(),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::QueryNode::*;
    use super::*;
    use rusqlite::types::{ToSqlOutput, ValueRef};

    macro_rules! query_test {
        ( $description:expr, $query:expr, $where_clause:expr, [$($params:expr),* $(,)?] $(,)?) => {
            ($description, $query, $where_clause.to_string(), vec_params![$($params),*])
        }
    }

    fn stringify_params(params: &Vec<Box<dyn rusqlite::ToSql>>) -> Vec<String> {
        params
            .iter()
            .map(|param| {
                let output = param.to_sql().unwrap();

                match output {
                    ToSqlOutput::Borrowed(ValueRef::Text(s)) => {
                        std::str::from_utf8(s).unwrap().to_string()
                    }
                    _ => format!("{:#?}", output),
                }
            })
            .collect()
    }

    #[test]
    fn queries_convert_correctly() {
        let tests = [
            query_test!("empty query", Empty {}, "1=1".to_string(), []),
            query_test!(
                "string equal",
                PropEqual {
                    name: "name".to_string(),
                    value: "value".into(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) = ?",
                ["value"],
            ),
            query_test!(
                "number equal",
                PropEqual {
                    name: "name".to_string(),
                    value: 42.into(),
                },
                "CAST(json_extract(properties, \"$.name\") AS NUMBER) = ?",
                [42],
            ),
            query_test!(
                "object-id equal",
                PropEqual {
                    name: "object-id".to_string(),
                    value: 42.into(),
                },
                "object_id = ?",
                [42],
            ),
            query_test!(
                "simple word like",
                PropLike {
                    name: "name".to_string(),
                    pattern: "phrase".to_string(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) REGEXP ?",
                [r"(?i)\bphrase\b"],
            ),
            query_test!(
                "prefix word like",
                PropLike {
                    name: "name".to_string(),
                    pattern: "phr*".to_string(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) REGEXP ?",
                [r"(?i)\bphr\w*\b"],
            ),
            query_test!(
                "suffix word like",
                PropLike {
                    name: "name".to_string(),
                    pattern: "*ase".to_string(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) REGEXP ?",
                [r"(?i)\b\w*ase\b"],
            ),
            query_test!(
                "mid-word like",
                PropLike {
                    name: "name".to_string(),
                    pattern: "*ras*".to_string(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) REGEXP ?",
                [r"(?i)\b\w*ras\w*\b"],
            ),
            query_test!(
                "multi-word like",
                PropLike {
                    name: "name".to_string(),
                    pattern: "lon* *hrase".to_string(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) REGEXP ?",
                [r"(?i)\blon\w*\b.*?\b\w*hrase\b"],
            ),
            query_test!(
                "anded queries",
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
                "CAST(json_extract(properties, \"$.name1\") AS TEXT) = ? AND CAST(json_extract(properties, \"$.name2\") AS TEXT) = ? AND CAST(json_extract(properties, \"$.name3\") AS TEXT) = ?",
                ["value1", "value2", "value3"],
            ),
        ];

        for (description, query, expected_where_clause, expected_params) in &tests {
            let (actual_where_clause, actual_params) = &query.to_sql_clause();

            assert_eq!(
                expected_where_clause, actual_where_clause,
                "{} where clause",
                description
            );
            assert_eq!(
                stringify_params(&expected_params),
                stringify_params(&actual_params),
                "{} params",
                description
            );
        }
    }
}

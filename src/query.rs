use rusqlite::ToSql;

use crate::object::PropValue;

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

pub trait QueryNode {
    fn to_sql_clause(&self) -> (String, Vec<Box<dyn ToSql>>);
}

#[derive(Debug)]
pub struct Empty {}

impl QueryNode for Empty {
    fn to_sql_clause(&self) -> (String, Vec<Box<dyn ToSql>>) {
        ("1=1".to_string(), vec_params![])
    }
}

#[derive(Debug)]
pub struct PropEqual {
    pub name: String,
    pub value: PropValue,
}

impl QueryNode for PropEqual {
    fn to_sql_clause(&self) -> (String, Vec<Box<dyn ToSql>>) {
        if self.name == "object-id" {
            return ("object_id = ?".to_string(), vec_params![self.value.clone()]);
        }

        let cast_type = match self.value {
            PropValue::String(_) => "TEXT",
            PropValue::Number(_) => "NUMBER",
        };

        (
            format!(
                "CAST(json_extract(properties, \"$.{}\") AS {}) = ?",
                self.name, cast_type
            )
            .to_string(),
            vec_params![self.value.clone()],
        )
    }
}

#[derive(Debug)]
pub struct PropLike {
    pub name: String,
    pub value: String,
}

impl QueryNode for PropLike {
    fn to_sql_clause(&self) -> (String, Vec<Box<dyn ToSql>>) {
        (
            format!(
                "CAST(json_extract(properties, \"$.{}\") AS TEXT) REGEXP ?",
                self.name
            )
            .to_string(),
            vec_params![format!(r"(?i)\b{}\b", self.value).to_string()],
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    macro_rules! query_test {
        ( $query:expr, $where_clause:expr, [$($params:expr),*] $(,)?) => {
            (Box::new($query) as Box<dyn QueryNode>, $where_clause.to_string(), vec_params![$($params,),*])
        }
    }

    #[test]
    fn queries_convert_correctly() {
        let tests = [
            query_test!(Empty {}, "1=1".to_string(), []),
            query_test!(
                PropEqual {
                    name: "name".to_string(),
                    value: "value".into(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) = ?",
                ["value"],
            ),
            query_test!(
                PropEqual {
                    name: "name".to_string(),
                    value: 42.into(),
                },
                "CAST(json_extract(properties, \"$.name\") AS NUMBER) = ?",
                [42],
            ),
            query_test!(
                PropEqual {
                    name: "object-id".to_string(),
                    value: 42.into(),
                },
                "object_id = ?",
                [42],
            ),
            query_test!(
                PropLike {
                    name: "name".to_string(),
                    value: "phrase".to_string(),
                },
                "CAST(json_extract(properties, \"$.name\") AS TEXT) REGEXP ?",
                [r"(?i)\bphrase\b"],
            ),
        ];

        for (query, expected_where_clause, expected_params) in &tests {
            let (actual_where_clause, actual_params) = &query.to_sql_clause();

            let expected_params_output: Vec<rusqlite::types::ToSqlOutput> = expected_params
                .iter()
                .map(|x| x.to_sql().unwrap())
                .collect();
            let actual_params_output: Vec<rusqlite::types::ToSqlOutput> =
                actual_params.iter().map(|x| x.to_sql().unwrap()).collect();

            assert_eq!(expected_where_clause, actual_where_clause);
            assert_eq!(expected_params_output, actual_params_output);
        }
    }
}

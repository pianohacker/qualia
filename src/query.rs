use rusqlite::ToSql;

macro_rules! vec_params {
    ($($param:expr),* $(,)?) => {
        vec![$(Box::new($param) as Box<dyn ToSql>),*]
    };
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
    pub value: String,
}

impl QueryNode for PropEqual {
    fn to_sql_clause(&self) -> (String, Vec<Box<dyn ToSql>>) {
        (
            format!("json_extract(properties, \"$.{}\") = ?", self.name).to_string(),
            vec_params![self.value.clone()],
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
                    value: "value".to_string(),
                },
                "json_extract(properties, \"$.name\") = ?",
                ["value"],
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

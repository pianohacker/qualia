use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum PropValue {
    Number(f64),
    String(String),
}

pub type Object = HashMap<String, PropValue>;

impl PropValue {
    pub fn as_str(&self) -> Option<&String> {
        match self {
            PropValue::String(s) => Some(s),
            _ => None,
        }
    }
}

impl From<serde_json::Value> for PropValue {
    fn from(x: serde_json::Value) -> Self {
        match x {
            serde_json::Value::String(s) => PropValue::String(s),
            serde_json::Value::Number(n) => PropValue::Number(n.as_f64().unwrap()),
            _ => {
                panic!("attempt to create PropValue from serde_json::Value not a Number or String")
            }
        }
    }
}

impl From<&serde_json::Value> for PropValue {
    fn from(x: &serde_json::Value) -> Self {
        PropValue::from(x.clone())
    }
}

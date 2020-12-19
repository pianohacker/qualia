#![macro_use]
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// All possible types that can be stored inside an [`Object`].
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum PropValue {
    Number(i64),
    String(String),
}

/// A set of properties that may be stored in a [`Store`](crate::Store).
pub type Object = HashMap<String, PropValue>;

/// Convenience macro for creating an [`Object`].
#[macro_export]
macro_rules! object {
    ( $($key:expr => $value:expr $(,)?)* ) => {{
        let mut object = Object::new();
        $(object.insert($key.into(), $value.into());)*
        object
    }};
    () => {
        Object::new()
    };
}

impl PropValue {
    /// If this [`PropValue`] contains a [`String`], return it. If not, return [`None`].
    pub fn as_str(&self) -> Option<&String> {
        match self {
            PropValue::String(s) => Some(s),
            _ => None,
        }
    }

    /// If this [`PropValue`] contains an [`i64`], return it. If not, return [`None`].
    pub fn as_number(&self) -> Option<i64> {
        match self {
            PropValue::Number(n) => Some(*n),
            _ => None,
        }
    }
}

impl From<serde_json::Value> for PropValue {
    fn from(x: serde_json::Value) -> Self {
        match x {
            serde_json::Value::String(s) => PropValue::String(s),
            serde_json::Value::Number(n) => PropValue::Number(n.as_i64().unwrap()),
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

impl<'a> From<&'a str> for PropValue {
    fn from(s: &str) -> Self {
        PropValue::String(s.to_string())
    }
}

impl From<String> for PropValue {
    fn from(s: String) -> Self {
        PropValue::String(s.clone())
    }
}

impl From<&String> for PropValue {
    fn from(s: &String) -> Self {
        PropValue::String(s.clone())
    }
}

impl From<i64> for PropValue {
    fn from(s: i64) -> Self {
        PropValue::Number(s.clone())
    }
}
